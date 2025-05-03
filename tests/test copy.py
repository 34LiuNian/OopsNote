import asyncio
from generate import Generate
from config import Env
from models import Request

async def main():
    env = Env()
    Generator = Generate(api_key=env.api_key, model=env.model, system_instruction=env.prompt, end_point=env.openai_endpoint, temperature=0.5)
    response = await Generator.generate(
        request=Request(
            image=open("data/telegram_bot/6669461026_20250502_102818_photo.jpg", 'rb').read(),
            image_path="",
            prompt="无"
        )
    )
    print(response)

if __name__ == "__main__":
    asyncio.run(main())