from dotenv import load_dotenv
import os

class Env:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv("GEMINI_MODEL")
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.api_key:
            raise ValueError("API key not found. Please set the GEMINI_API_KEY environment variable.")
        if not self.model:
            raise ValueError("Model name not found. Please set the GEMINI_MODEL environment variable.")
        # 读取提示文件
        with open("./prompt.md", 'r', encoding='utf-8') as f:
            self.prompt = f.read()
