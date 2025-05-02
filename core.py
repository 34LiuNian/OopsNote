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

class OopsNote:
    def __init__(self):
        """
        初始化
        创建相关模块实例
        尝试加载上次未处理的队列
        """
        # TODO: 配置化文件创建
        os.makedirs("./data/telegram_bot", exist_ok=True)
        os.makedirs("./data/markdown", exist_ok=True)
        os.makedirs("./data", exist_ok=True) # 确保 data 目录存在

        self.env = Env()

        self.queue: asyncio.Queue[Request] = asyncio.Queue()
        
        # 使用具体的持久化实现
        self.queue_persistence: QueuePersistence = PickleFileQueuePersistence(QUEUE_DUMP_FILE)
        self.queue_persistence.load_queue(self.queue) # <--- 使用新的调用

        self.Generator = generate.Generate(mode=self.env.api_mode, api_key=self.env.api_key, model=self.env.model, system_instruction=self.env.prompt, end_point=self.env.openai_endpoint, tempterature=0.5)

        self.Saver = MongoSaver()

        # self.Explorter = MarkdownExporter(output_dir="data/markdown") # TODO: 导出的core完善

        self.Bot = telegram_bot.Bot(token=self.env.telegram_token, Queue=self.queue)

    async def deal_request(self):
        """
        处理请求，分析数据并生成内容
        """
        while True:
            try:
                data = await self.queue.get()
                if data is None: # 停止信号处理 (虽然我们现在主要靠取消)
                    logger.info("收到停止信号， deal_request 退出。")
                    break # 退出循环
                try:
                    # 调用 AI 生成
                    wrong: OopsResponse = self.Generator.generate(data)
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
                    logger.error(f"处理请求 (Prompt: {data.prompt}) 时发生错误: {e}")
            except asyncio.CancelledError:
                logger.info("deal_request 任务被取消，正在退出...")
                break # 捕获取消信号并退出循环
            finally:
                # 确保即使在取消或出错时也调用 task_done
                # 如果 get() 被取消，可能没有 item，所以需要检查
                if 'data' in locals() and data is not None:
                    try:
                        self.queue.task_done()
                    except ValueError: # 可能已经被 task_done
                        pass


    async def shutdown(self, loop: asyncio.AbstractEventLoop, task_bot: asyncio.Task, task_deal: asyncio.Task):
        """
        关闭程序，保存队列状态并取消任务
        """
        logger.info("开始执行关闭程序...")

        self.queue_persistence.save_queue(self.queue) # <--- 使用新的调用

        self.Saver.close()

        logger.info("正在取消后台任务...")
        tasks_to_cancel = [task_bot, task_deal]
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()

        cancelled_tasks = await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        for i, result in enumerate(cancelled_tasks):
            task_name = "task_bot" if i == 0 else "task_deal"
            if isinstance(result, asyncio.CancelledError):
                logger.info(f"{task_name} 已成功取消。")
            elif isinstance(result, Exception):
                logger.error(f"取消 {task_name} 时发生错误: {result}")
            else:
                 logger.info(f"{task_name} 在取消前已完成。") # 或者正常结束了

        logger.info("关闭程序完成。")


    async def launch(self):
        """
        启动主程序，创建任务并运行
        """
        loop = asyncio.get_running_loop()
        task_bot = None
        task_deal = None

        try:
            # 创建两个异步任务
            task_bot = asyncio.create_task(self.Bot.run())
            task_deal = asyncio.create_task(self.deal_request())
            
            # 让两个任务真正并行执行，而不是等待任一任务完成
            # 使用 asyncio.gather 等待所有任务完成（但实际上它们是无限循环，除非有异常或被取消）
            await asyncio.gather(task_bot, task_deal)
            
            # 注：上面的 gather 实际上永远不会正常结束，因为两个任务都是无限循环
            # 所以下面的代码只有在异常（如Ctrl+C）时才会执行

        except asyncio.CancelledError:
            logger.info("主任务被取消 (可能由 Ctrl+C 触发)，开始清理...")
        except Exception as e:
            logger.error(f"运行时发生异常: {e}", exc_info=True)
        finally:
            await self.shutdown(loop, task_bot, task_deal)