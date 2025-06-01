from queue_persistence import PickleFileQueuePersistence, QueuePersistence
from models import OopsResponse, Request, Oops
# from export import MarkdownExporter # TODO: 模块名
from save import MongoSaver
from config import Env
import telegram_bot
import generate

import asyncio
from logger import logging

logger = logging.getLogger(__name__)


class OopsNote:
    def __init__(self, enable_bot: bool = True, max_workers: int = 4, threshold: int = 5):
        """
        初始化
        创建相关模块实例
        尝试加载上次未处理的队列
        """
        self.env = Env()
        self.queue: asyncio.Queue[Request] = asyncio.Queue()
        self.queue_persistence: QueuePersistence = PickleFileQueuePersistence(self.env.dump_file)
        self.Generator = generate.Generate(api_mode=self.env.api_mode, api_key=self.env.api_key, model=self.env.model, system_instruction=self.env.system_instruction, end_point=self.env.endpoint, temperature=self.env.temperature)
        self.Saver = MongoSaver()
        self.enable_bot = enable_bot
        self.max_workers = max_workers
        self.threshold = threshold
        self.workers: list[asyncio.Task] = []
        if self.enable_bot:
            self.Bot = telegram_bot.Bot(token=self.env.telegram_token, Queue=self.queue)
        else:
            self.Bot = None

    async def deal_request(self):
        data = None
        """
        处理请求，分析数据并生成内容
        """
        try:
            while True:
                data = await self.queue.get()
                if data is None:
                    # None 作为停止信号
                    self.queue.task_done()
                    break
                try:
                    wrong: OopsResponse = await self.Generator.generate(data)
                    # logger.info(f"生成的内容：\n{wrong.problem}")
                    oops_to_save = Oops(
                        problem=wrong.problem,
                        answer=wrong.answer,
                        analysis=wrong.analysis,
                        tags=wrong.tags,
                        image_path=data.image_path
                    )

                    self.Saver.save_oops(oops_to_save)
                    logger.info(f"请求处理完毕并成功保存。")
                except Exception as e:
                    logger.error(
                        f"处理请求 (Prompt: {getattr(data, 'prompt', '')}) 时发生错误: {e}",
                        exc_info=True,
                    )
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            if data is not None:
                self.queue.put_nowait(data)  # 将未处理的请求放回队列
            logger.info("处理请求的任务被取消。")
        except Exception as e:
            logger.error(f"处理请求时发生异常: {e}", exc_info=True)
        finally:
            self.queue_persistence.save_queue(self.queue)
            logger.info("队列已保存。")

    async def _monitor_workers(self):
        """根据队列长度动态调整处理协程数量"""
        try:
            while True:
                await asyncio.sleep(1)
                qsize = self.queue.qsize()
                # 清理已结束的任务
                self.workers = [w for w in self.workers if not w.done()]
                target = min(self.max_workers, max(1, (qsize // self.threshold) + 1))
                while len(self.workers) < target:
                    task = asyncio.create_task(self.deal_request())
                    self.workers.append(task)
                    logger.info(f"新增处理线程，当前数量: {len(self.workers)}")
        except asyncio.CancelledError:
            pass
        finally:
            for _ in self.workers:
                self.queue.put_nowait(None)
            await asyncio.gather(*self.workers, return_exceptions=True)

    async def launch(self):
        """
        启动主程序，创建任务并运行
        """
        task_bot = None
        monitor = None

        try:
            self.queue_persistence.load_queue(self.queue)

            if self.Bot:
                task_bot = asyncio.create_task(self.Bot.run())
            monitor = asyncio.create_task(self._monitor_workers())

            await asyncio.gather(*(t for t in [task_bot, monitor] if t))
            
        except KeyboardInterrupt:
            logger.info("Ctrl+C 退出，开始清理...")
            for _ in self.workers:
                self.queue.put_nowait(None)
            if monitor:
                monitor.cancel()
            await asyncio.gather(*self.workers, return_exceptions=True)
            if task_bot:
                task_bot.cancel()
                await asyncio.gather(task_bot, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("任务被取消，退出 launch。")
            for _ in self.workers:
                self.queue.put_nowait(None)
            if monitor:
                monitor.cancel()
            await asyncio.gather(*self.workers, return_exceptions=True)
        except Exception as e:
            logger.error(f"运行时发生异常: {e}", exc_info=True)
        finally:
            self.Saver.close()
            logger.info("程序已退出。")