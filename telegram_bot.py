from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from models import Request
import asyncio
from logger import logging
logger = logging.getLogger(__name__)
# 8109
# TODO: 防止被攻击
class Bot:
    """
    Telegram Bot 类，用于处理用户发送的图片和命令。
    """
    def __init__(self, token: str, Queue: asyncio.Queue[Request]):
        logger.info("Telegram Bot 初始化中...")
        self.token = token
        self.queue = Queue

        self.application = ApplicationBuilder().token(token).build()
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        logger.info("Telegram Bot 初始化完成。")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE): # context不是冗余的， 下同
        await update.message.reply_text("发送图片以开始错题整理，可携带描述")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user
        photo = update.message.photo[-1]
        caption = update.message.caption or ""
        photo_file = await photo.get_file()

        # TODO: 优化图片保存
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"./data/telegram_bot/{user.id}_{timestamp}_photo.jpg"

        await photo_file.download_to_drive(file_path)

        logger.info("用户 %s 发送了图片，描述：%s ，已保存为 %s。", user.first_name, caption, file_path)
        await update.message.reply_text(f"图片已收到，准备分析...")
        await self.queue.put(Request(
            image=open(file_path, 'rb').read(),
            image_path=file_path,
            prompt=caption, 
        ))
        logger.info("请求已放入队列。")


    async def run(self):
        """异步启动 Bot 并保持运行。"""
        try:
            logger.info("Telegram Bot 启动中...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            logger.info("Telegram Bot 运行中，等待消息...")

            stop_signal = asyncio.get_event_loop().create_future()
            await stop_signal
        except asyncio.CancelledError:
            logger.info("Telegram Bot 运行已取消。")  # TODO: 处理异常优化（Ctrl+C）
        except Exception as e:  # 捕获网络或初始化失败等异常
            logger.error("Telegram Bot 启动或运行时发生异常: %s", e, exc_info=True)
        finally:
            logger.info("Telegram Bot 关闭中...")
            try:
                if getattr(self.application, "updater", None):
                    await self.application.updater.stop()
            except Exception:
                pass
            try:
                await self.application.stop()
            except Exception:
                pass
            try:
                await self.application.shutdown()
            except Exception:
                pass
            logger.info("Telegram Bot 已关闭。")
