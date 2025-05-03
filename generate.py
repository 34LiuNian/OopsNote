# from openai import AsyncOpenAI
from models import OopsResponse, Request
from pydantic import TypeAdapter
from logger import logging
import base64
import asyncio
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class Generate:
    def __init__(self, api_key: str, model: str, system_instruction: str, end_point: str = None, temperature: float = 0.5):
        logger.info("生成器初始化中...")
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.end_point = end_point
        self.api_key = api_key
        self.model = model

        logger.info("end_point: %s", self.end_point)
        logger.info("model: %s", self.model)
        logger.info("temperature: %s", self.temperature)

        self.client = genai.Client(
            api_key=self.api_key,
            http_options={"base_url": "https://aihubmix.com/gemini"}
        )
        logger.info("生成器初始化完成。")

    async def generate(self, request: Request) -> OopsResponse:
        """
        异步 Gemini 实现
        """
        logger.info("准备调用 Gemini API ...")
        file_bytes = base64.b64encode(request.image).decode('utf-8')

        contents = types.Content(
            parts=[
                types.Part(
                    inline_data=types.Blob(
                        data=file_bytes,
                        mime_type="image/jpeg"
                    )
                ),
                types.Part(
                    text=request.prompt,
                )
            ]
        )
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction = self.system_instruction,
                temperature = self.temperature,
                response_mime_type = 'application/json',
                response_schema = OopsResponse,
            )
        )
        logger.info("Gemini API 调用完成，正在解析结果...")
        parsed = response.parsed
        logger.info("Gemini 结果解析成功。")
        return parsed
