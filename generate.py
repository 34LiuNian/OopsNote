# from openai import AsyncOpenAI
from models import OopsResponse, Request
from pydantic import TypeAdapter
from logger import logging
import asyncio
from google import genai
from google.genai import types
import base64
import json
import urllib.request

logger = logging.getLogger(__name__)

class Generate:
    def __init__(self, api_mode: str, api_key: str, model: str, system_instruction: str, end_point: str = None, temperature: float = 0.5):
        logger.info("生成器初始化中...")
        self.api_mode = api_mode.upper()
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.end_point = end_point
        self.api_key = api_key
        self.model = model

        logger.info("end_point: %s", self.end_point)
        logger.info("model: %s", self.model)
        logger.info("api_mode: %s", self.api_mode)

        if self.api_mode == "GEMINI":
            self.client = genai.Client(
                api_key=self.api_key,
                http_options={"base_url": self.end_point or "https://aihubmix.com/gemini"}
            )
        else:
            self.client = None  # 其他模式在调用时处理

        logger.info("生成器初始化完成。")

    async def generate(self, request: Request) -> OopsResponse:
        """根据不同 API 调用相应的生成接口"""
        if self.api_mode == "GEMINI":
            logger.info("准备调用 Gemini API ...")
            file_bytes = request.image
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
                    system_instruction=self.system_instruction,
                    temperature=self.temperature,
                    response_mime_type='application/json',
                    response_schema=OopsResponse,
                )
            )
            logger.info("Gemini API 调用完成，正在解析结果...")
            parsed = response.parsed
            logger.info("Gemini 结果解析成功。")
            return parsed
        elif self.api_mode == "QWEN3":
            logger.info("准备调用 Qwen3 API ...")
            image_b64 = base64.b64encode(request.image).decode()
            payload = {
                "model": self.model,
                "input": {
                    "messages": [
                        {"role": "system", "content": self.system_instruction},
                        {"role": "user", "content": [{"image": image_b64}, request.prompt]}
                    ]
                },
                "parameters": {"temperature": self.temperature, "result_format": "json"}
            }
            req = urllib.request.Request(
                self.end_point,
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
            )
            response = await asyncio.to_thread(urllib.request.urlopen, req)
            data = json.loads(response.read())
            logger.info("Qwen3 API 调用完成，正在解析结果...")
            content = json.loads(data.get("output", "{}"))
            return OopsResponse.model_validate(content)
        else:
            raise NotImplementedError(f"Unsupported api_mode: {self.api_mode}")
