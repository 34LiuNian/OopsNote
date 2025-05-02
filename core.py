from models import OopsResponse, Request, Oops
from export import MarkdownExporter # TODO: 模块改名，防混淆
from save import MongoSaver
from config import Env
import telegram_bot
import generate
from queue_persistence import PickleFileQueuePersistence, QueuePersistence

import asyncio
import os
from logger import logging

logger = logging.getLogger(__name__)

QUEUE_DUMP_FILE = "data/queue_state.pkl"
WORKER_COUNT = 5 # 同时处理的最大任务数

class OopsNote:
    def __init__(self):
        """
        初始化
        创建相关模块实例
        尝试加载上次未处理的队列
        """

        self.env = Env()

        self.queue: asyncio.Queue[Request] = asyncio.Queue()
        self.processing_semaphore = asyncio.Semaphore(WORKER_COUNT)
        
        # 持久化实现
        self.queue_persistence: QueuePersistence = PickleFileQueuePersistence(QUEUE_DUMP_FILE)
        self.queue_persistence.load_queue(self.queue)

        self.Generator = generate.Generate(mode=self.env.api_mode, api_key=self.env.api_key, model=self.env.model, system_instruction=self.env.prompt, end_point=self.env.openai_endpoint, tempterature=0.5)

        self.Saver = MongoSaver()

        # self.Explorter = MarkdownExporter(output_dir="data/markdown") # TODO: 导出的core完善

        self.Bot = telegram_bot.Bot(token=self.env.telegram_token, Queue=self.queue)

    async def deal_request(self):
        """
        处理请求，分析数据并生成内容 (单个 worker 的逻辑)
        """
        while True:
            try:
                data = await self.queue.get()
                if data is None: # 停止信号处理
                    logger.info("收到停止信号， deal_request worker 退出。")
                    # 将 None 放回队列，以便其他 worker 也能收到信号
                    # 注意：这在多 worker 场景下可能导致队列中积压 None
                    # 更好的方式是依赖任务取消
                    # await self.queue.put(None)
                    break # 退出循环

                async with self.processing_semaphore: # 获取信号量，限制并发
                    try:
                        # 调用 AI 生成 (现在是异步的)
                        wrong: OopsResponse = await self.Generator.generate(data)
                        logger.info(f"生成的内容：\n{wrong.problem}")

                        # 构建 Oops 对象 (需要包含 image_path)
                        oops_to_save = Oops(
                            problem=wrong.problem,
                            answer=wrong.answer,
                            analysis=wrong.analysis,
                            tags=wrong.tags,
                            image_path=data.image_path # 从原始请求中获取 image_path
                        )

                        # 保存到数据库
                        self.Saver.save_oops(oops_to_save)
                        logger.info(f"请求处理完毕并成功保存。")

                    except Exception as e:
                        logger.error(f"处理请求 (Prompt: {data.prompt}) 时发生错误: {e}", exc_info=True) # 添加 exc_info=True 获取更详细的回溯
                    finally:
                        # 确保即使在内部处理出错时也调用 task_done
                        try:
                            self.queue.task_done()
                        except ValueError: # 可能已经被 task_done
                            pass

            except asyncio.CancelledError:
                logger.info("deal_request worker 任务被取消，正在退出...")
                break # 捕获取消信号并退出循环
            except Exception as e:
                logger.error(f"deal_request worker 发生意外错误: {e}", exc_info=True)
                # 如果 get() 出错，可能需要退出循环或添加延迟重试
                await asyncio.sleep(1) # 简单延迟


    async def shutdown(self, loop: asyncio.AbstractEventLoop, task_bot: asyncio.Task, tasks_deal: list[asyncio.Task]):
        """
        关闭程序，保存队列状态并取消任务
        """
        logger.info("关闭程序...")

        # 1. 先尝试清空并保存队列
        self.queue_persistence.save_queue(self.queue)

        # 2. 关闭数据库连接
        self.Saver.close()

        # 3. 取消所有后台任务
        logger.info("正在取消后台任务...")
        tasks_to_cancel = [task_bot] + tasks_deal # 合并任务列表
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()

        # 等待所有任务完成取消
        cancelled_tasks = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        
        # 记录取消结果
        task_names = ["task_bot"] + [f"task_deal_{i}" for i in range(len(tasks_deal))]
        for name, result in zip(task_names, cancelled_tasks):
            if isinstance(result, asyncio.CancelledError):
                logger.info(f"{name} 已成功取消。")
            elif isinstance(result, Exception):
                logger.error(f"取消 {name} 时发生错误: {result}", exc_info=True)
            else:
                 logger.info(f"{name} 在取消前已完成或正常结束。")

        logger.info("关闭程序完成。")


    async def launch(self):
        """
        启动主程序，创建任务并运行
        """
        loop = asyncio.get_running_loop()
        task_bot = None
        tasks_deal = [] # 改为列表存储 deal 任务

        try:
            # 创建 Telegram Bot 任务
            task_bot = asyncio.create_task(self.Bot.run())
            
            # 创建多个处理请求的 worker 任务
            tasks_deal = [asyncio.create_task(self.deal_request()) for _ in range(WORKER_COUNT)]
            logger.info(f"启动了 {WORKER_COUNT} 个请求处理 worker。")
            
            # 使用 asyncio.gather 等待所有核心任务（理论上是无限运行）
            all_tasks = [task_bot] + tasks_deal
            await asyncio.gather(*all_tasks)
            
        except asyncio.CancelledError:
            logger.info("主任务被取消 (可能由 Ctrl+C 触发)，开始清理...")
        except Exception as e:
            logger.error(f"运行时发生异常: {e}", exc_info=True)
        finally:
            # 确保传入任务列表
            await self.shutdown(loop, task_bot, tasks_deal)