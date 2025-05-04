from dotenv import load_dotenv
import os
from logger import logging
logger = logging.getLogger(__name__)
class Env:
    def __init__(self):

        # TODO: 配置化文件创建
        os.makedirs("./data/telegram_bot", exist_ok=True)
        os.makedirs("./data/markdown", exist_ok=True)
        os.makedirs("./data", exist_ok=True) # 确保 data 目录存在

        logger.info("加载环境变量...")
        try:
            load_dotenv()
        except FileNotFoundError:
            logger.error("未找到 .env 文件，请确保该文件存在于当前目录。")
            raise FileNotFoundError("未找到 .env 文件，请确保该文件存在于当前目录。")

        self.api_mode = os.getenv("API_MODE", "GEMINI")
        if self.api_mode == "GEMINI":
            self.api_key = os.getenv("GEMINI_API_KEY")
            self.endpoint = os.getenv("GEMINI_ENDPOINT")
            self.model = os.getenv("GEMINI_MODEL")
        else:
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.endpoint = os.getenv("OPENAI_ENDPOINT")
            self.model = os.getenv("OPENAI_MODEL")
        self.temperature = float(os.getenv("TEMPERATURE", 0.5))

        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

        self.mongo_uri = os.getenv("MONGO_URI")
        self.database_name = os.getenv("DATABASE_NAME")

        self.dump_file = os.getenv("DUMP_FILE") # 队列持久化文件

        # 读取提示文件
        with open(os.getenv("PROMPT_FILE"), 'r', encoding='utf-8') as f:
            self.system_instruction = f.read()
        logger.info("环境变量加载完成。")
