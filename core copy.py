# TODO: 修改导入方式，以优化实例命名
from models import OopsResponse, Request, Oops
from markdown import save_markdown# TODO: 模块改名，防混淆
from save import MongoSaver
from config import Env
import telegram_bot
import generate

from datetime import datetime
import asyncio
import os
import pickle
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
        self._load_queue()

        self.Generater = generate.Generate(mode=self.env.api_mode, api_key=self.env.api_key, model=self.env.model, system_instruction=self.env.prompt)

        self.Saver = MongoSaver()

        self.Bot = telegram_bot.Bot(token=self.env.telegram_token, Queue=self.queue)

    def _load_queue(self):
        """
        从文件加载上次未完成的队列任务
        """
        if os.path.exists(QUEUE_DUMP_FILE):
            try:
                with open(QUEUE_DUMP_FILE, 'rb') as f:
                    items = pickle.load(f)
                for item in items:
                    # 注意：这里假设 Request 对象是可序列化的
                    # 如果 Request 包含不可序列化的内容（如文件句柄），需要调整
                    # 这里直接放入 Request 对象，因为图片数据已是 bytes
                    self.queue.put_nowait(item)
                logger.info(f"成功从 {QUEUE_DUMP_FILE} 加载了 {len(items)} 个未处理的任务。")
                os.remove(QUEUE_DUMP_FILE) # 加载成功后删除文件，避免重复加载
                logger.info(f"已删除队列状态文件: {QUEUE_DUMP_FILE}")
            except (FileNotFoundError, pickle.UnpicklingError, EOFError, TypeError) as e:
                logger.error(f"加载队列状态文件 {QUEUE_DUMP_FILE} 失败: {e}。将启动空队列。")
            except Exception as e:
                 logger.error(f"加载队列时发生未知错误: {e}。将启动空队列。")


    def _save_queue(self):
        """
        将当前队列中未处理的任务保存到文件
        """
        items_to_save = []
        while not self.queue.empty():
            try:
                # 使用 get_nowait 避免阻塞
                item = self.queue.get_nowait()
                # 确保 None 信号不被保存
                if item is not None:
                    items_to_save.append(item)
                # 标记任务完成，即使我们没有处理它，因为我们要保存它
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break # 队列已空
            except Exception as e:
                logger.error(f"从队列取出任务准备保存时出错: {e}")
                # 出错时也标记完成，避免卡住 join (虽然我们不用 join 了)
                try:
                    self.queue.task_done()
                except ValueError: # 如果任务已被标记完成
                    pass

        if items_to_save:
            try:
                with open(QUEUE_DUMP_FILE, 'wb') as f:
                    pickle.dump(items_to_save, f)
                logger.info(f"成功将 {len(items_to_save)} 个未处理的任务保存到 {QUEUE_DUMP_FILE}。")
            except (pickle.PicklingError, IOError) as e:
                logger.error(f"保存队列状态到 {QUEUE_DUMP_FILE} 失败: {e}")
            except Exception as e:
                 logger.error(f"保存队列时发生未知错误: {e}")
        else:
            logger.info("队列为空，无需保存状态。")


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
                    wrong: OopsResponse = self.Generater.generate(data) # 修正：调用 generate 而不是 gemerate
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
        优雅关闭程序，保存队列状态并取消任务
        """
        logger.info("开始执行关闭程序...")

        # 1. 保存队列状态
        self._save_queue()

        # 2. 关闭数据库连接
        self.Saver.close()

        # 3. 取消正在运行的任务
        logger.info("正在取消后台任务...")
        tasks_to_cancel = [task_bot, task_deal]
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()

        # 等待任务被取消 (给它们一点时间清理)
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
            task_bot = asyncio.create_task(self.Bot.run())
            task_deal = asyncio.create_task(self.deal_request())
            # 等待任一任务完成或被取消
            # 使用 wait 而不是 gather，这样可以更容易处理取消
            done, pending = await asyncio.wait(
                [task_bot, task_deal],
                return_when=asyncio.FIRST_COMPLETED # 或者 FIRST_EXCEPTION
            )
            # 如果有任务异常结束，记录日志
            for task in done:
                try:
                    task.result() # 获取结果，如果异常会抛出
                except asyncio.CancelledError:
                    pass # 被取消是预期的
                except Exception as e:
                    task_name = "task_bot" if task == task_bot else "task_deal"
                    logger.error(f"{task_name} 异常退出: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("主任务被取消 (可能由 Ctrl+C 触发)，开始清理...")
        finally:
            # 调用新的关闭函数
            await self.shutdown(loop, task_bot, task_deal)