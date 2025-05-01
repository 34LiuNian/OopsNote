from dotenv import load_dotenv
import os
from logger import logging
logger = logging.getLogger(__name__)
class Env:
    def __init__(self):
        logger.info("加载环境变量...")
        try:
            # 尝试加载 .env 文件
            load_dotenv()
        except FileNotFoundError:
            logger.error("未找到 .env 文件，请确保该文件存在于当前目录。")
            raise FileNotFoundError("未找到 .env 文件，请确保该文件存在于当前目录。")

        self.api_mode = os.getenv("API_MODE")
        if self.api_mode == "GEMINI":
            self.api_key = os.getenv("GEMINI_API_KEY")
            self.model = os.getenv("GEMINI_MODEL")
        elif self.api_mode == "OPENAI":
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.model = os.getenv("OPENAI_MODEL")
        
        else:
            # logger.error("处理失败", exc_info=True) #TODO： 添加异常处理
            raise ValueError("Invalid API mode. Please set GEMINI_API_MODE to either 'GEMINI' or 'OPENAI'.")
        self.openai_endpoint = os.getenv("OPENAI_ENDPOINT") #TODO： 需要添加特判
        if not self.api_key:
            raise ValueError("API key not found. Please set the GEMINI_API_KEY environment variable.")
        if not self.model:
            raise ValueError("Model name not found. Please set the GEMINI_MODEL environment variable.")
        
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

        self.mongo_uri = os.getenv("MONGO_URI")
        self.database_name = os.getenv("DATABASE_NAME")

        # 读取提示文件
        with open(os.getenv("PROMPT_FILE"), 'r', encoding='utf-8') as f:
            self.prompt = f.read()
        logger.info("环境变量加载完成。")
