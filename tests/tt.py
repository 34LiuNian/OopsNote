import asyncio
from google import genai
from google.genai import types

async def main():
    # 读取文件为二进制数据
    file_path = "data/telegram_bot/6669461026_20250502_222027_photo.jpg"
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    client = genai.Client(
        api_key="sk-WkYTI6iPaFDAqQdMFd612bD34eAc4e918cC8F5Bf5cC86d8e", # 🔑 换成你在 AiHubMix 生成的密钥
        http_options={"base_url": "https://aihubmix.com/gemini"}
    )



if __name__ == "__main__":
    asyncio.run(main())