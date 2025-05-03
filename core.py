from models import OopsResponse, Request, Oops
# from export import MarkdownExporter # TODO: 模块改名，防混淆
from save import MongoSaver
from config import Env
import telegram_bot
import generate
from queue_persistence import PickleFileQueuePersistence, QueuePersistence

import asyncio
from logger import logging

logger = logging.getLogger(__name__)


class OopsNote:
    def __init__(self):
        """
        初始化
        创建相关模块实例
        尝试加载上次未处理的队列
        """

        self.env = Env()

        self.queue: asyncio.Queue[Request] = asyncio.Queue()
        
        # 持久化实现
        # self.queue_persistence: QueuePersistence = PickleFileQueuePersistence(QUEUE_DUMP_FILE)
        # self.queue_persistence.load_queue(self.queue)

        self.Generator = generate.Generate(api_key=self.env.api_key, model=self.env.model, system_instruction=self.env.prompt, end_point=self.env.openai_endpoint, temperature=0.5)

        self.Saver = MongoSaver()

        # self.Exporter = MarkdownExporter(output_dir="data/markdown") # TODO: 导出的core完善

        self.Bot = telegram_bot.Bot(token=self.env.telegram_token, Queue=self.queue)

    async def deal_request(self):
        """
        处理请求，分析数据并生成内容
        """
        while True:
            data = await self.queue.get()
            wrong: OopsResponse = await self.Generator.generate(data)
            logger.info(f"生成的内容：\n{wrong.problem}")
            oops_to_save = Oops(
                problem=wrong.problem,
                answer=wrong.answer,
                analysis=wrong.analysis,
                tags=wrong.tags,
                image_path=data.image_path 
            )

            self.Saver.save_oops(oops_to_save)
            logger.info(f"请求处理完毕并成功保存。")


    async def shutdown(self, task_bot: asyncio.Task):
        """
        关闭程序，保存队列状态并取消任务
        """
        logger.info("关闭程序...")

        # self.queue_persistence.save_queue(self.queue)
        self.Saver.close()

        if task_bot:
            task_bot.cancel()
            try:
                await task_bot
            except asyncio.CancelledError:
                logger.info("Bot 任务已取消。")

        logger.info("关闭程序完成。")


    async def launch(self):
        """
        启动主程序，创建任务并运行
        """
        task_bot = None

        try:
            task_bot = asyncio.create_task(self.Bot.run())
            
            tasks_deal = asyncio.create_task(self.deal_request())
            
            await asyncio.gather(task_bot, tasks_deal)
            
        except asyncio.CancelledError:
            logger.info("主任务被取消 (可能由 Ctrl+C 触发)，开始清理...")
        except Exception as e:
            logger.error(f"运行时发生异常: {e}", exc_info=True)
        finally:
            # 确保传入任务列表
            await self.shutdown(task_bot, tasks_deal)