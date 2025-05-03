import asyncio
from google import genai
from google.genai import types
from pydantic import BaseModel
  

class Tags(BaseModel):
    class Problem(BaseModel):
        subject: str
        question_type: str
        difficulty: str
        knowledge_point: list[str]
        
    class Answer(BaseModel):
        answer_status: str
        error_type: str
        correction_status: str

    problem: Problem
    answer: Answer
class OopsResponse(BaseModel):
    problem: str
    answer: str
    analysis: str
    tags: Tags


async def generate() -> OopsResponse:
    """
    异步 Gemini 实现
    """
    file_path = "data/telegram_bot/6669461026_20250502_222027_photo.jpg"
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    contents = types.Content(
        parts=[
            types.Part(
                inline_data=types.Blob(
                    data=file_bytes,
                    mime_type="image/jpeg"
                )
            ),
            types.Part(
                text=""
            )
        ]
    )
    client = genai.Client(
        api_key="sk-WkYTI6iPaFDAqQdMFd612bD34eAc4e918cC8F5Bf5cC86d8e", # 🔑 换成你在 AiHubMix 生成的密钥
        http_options={"base_url": "https://aihubmix.com/gemini"}
    )
    response = await client.aio.models.generate_content(
        model="gemini-2.5-pro-exp-03-25",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction = "你是一个优秀的数学老师，擅长分析图片中的数学题目，并给出详细的解答和分析。",
            temperature = 0.5,
            response_mime_type = 'application/json',
            response_schema = OopsResponse,
        )
    )
    parsed = response.parsed
    print(parsed)
    return parsed

if __name__ == "__main__":
    asyncio.run(generate())