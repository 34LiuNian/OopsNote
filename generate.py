import asyncio # 添加 asyncio
from models import OopsResponse, Request # OopsResponse 而不是 Response
from pydantic import TypeAdapter
from google import genai
from logger import logging
import openai
import base64 # 添加 base64

logger = logging.getLogger(__name__)

class Generate:
    def __init__(self, mode: str, api_key: str, model: str, system_instruction: str, end_point: str = None, tempterature: float = 0.5):
        logger.info("生成器初始化中...")
        self.system_instruction = system_instruction
        self.tempterature = tempterature
        self.end_point = end_point
        self.api_key = api_key
        self.model = model
        self.mode = mode
        # self.client = genai.GenerativeModel(model_name=self.model, api_key=self.api_key, system_instruction=self.system_instruction)
        openai.api_key = self.api_key
        if self.end_point:
            openai.api_base = self.end_point
        logger.info("生成器初始化完成。")


    async def generate(self, request: Request) -> OopsResponse:
        """
        异步匹配生成模式
        """
        logger.info(f"开始异步调用生成 ({self.mode})...")
        if self.mode == "GEMINI":
            # return await self.gemini_generate(request)
            pass
        elif self.mode == "OPENAI":
            return await self.openai_compatible_generate(request)
        else:
            logger.error(f"未知的生成模式: {self.mode}")
            # Consider raising an error or returning a default error response
            raise ValueError(f"未知的生成模式: {self.mode}")

    # async def gemini_generate(self, request: Request) -> OopsResponse:
    #     """
    #     异步 Gemini 实现
    #     Note: google-genai might not have a direct async client.
    #     Using asyncio.to_thread to run the synchronous call in a separate thread.
    #     If google-generativeai is used, it has generate_content_async.
    #     """
    #     logger.info("准备调用 Gemini API...")
    #     contents = [
    #         {
    #             "role": "user",
    #             "parts": [
    #                 {"mime_type": "image/jpeg", "data": request.image},
    #                 {"text": request.prompt}
    #             ]
    #         }
    #     ]
    #     generation_config = genai.types.GenerationConfig(
    #         response_mime_type="application/json",
    #         temperature=self.tempterature
    #         # response_schema is not directly in GenerationConfig for the sync client's generate_content
    #         # We rely on the model understanding the JSON output format instruction.
    #     )

    #     try:
    #         # Run the synchronous generate_content in a separate thread
    #         response = await asyncio.to_thread(
    #             self.client.generate_content,
    #             contents=contents,
    #             generation_config=generation_config
    #             # system_instruction is set during client init
    #         )

    #         logger.info("Gemini API 调用完成，正在解析结果...")
    #         # Assuming response.text contains the JSON string
    #         json_data = response.text
    #         parsed = TypeAdapter(OopsResponse).validate_json(json_data)
    #         logger.info("Gemini 结果解析成功。")
    #         return parsed
    #     except Exception as e:
    #         logger.error(f"Gemini API 调用或解析失败: {e}", exc_info=True)
    #         # Re-raise or return an error response
    #         raise


    async def openai_compatible_generate(self, request: Request) -> OopsResponse:
        """
        异步 OpenAI 实现 (使用 asyncio.to_thread)
        """
        logger.info("准备调用 OpenAI API...")
        # Encode image to base64
        base64_image = base64.b64encode(request.image).decode('utf-8')
        base64_image_url = f"data:image/jpeg;base64,{base64_image}"

        messages = [
            {"role": "system", "content": self.system_instruction},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": base64_image_url,
                            "detail": "high", # Detail level can be adjusted
                        },
                    },
                    {
                        "type": "text",
                        "text": request.prompt,
                    },
                ],
            },
        ]

        try:
            # Define the synchronous function call
            def sync_openai_call():
                return openai.chat.completions.create( # Use the newer client syntax if available
                    model=self.model,
                    messages=messages,
                    temperature=self.tempterature,
                    response_format={"type": "json_object"} # Request JSON output
                )

            # Run the synchronous call in a separate thread
            response = await asyncio.to_thread(sync_openai_call)

            logger.info("OpenAI API 调用完成，正在解析结果...")
            # Extract JSON string from the response
            # Adjust based on the actual structure of the response object
            json_data = response.choices[0].message.content
            parsed = TypeAdapter(OopsResponse).validate_json(json_data)
            logger.info("OpenAI 结果解析成功。")
            return parsed
        except Exception as e:
            logger.error(f"OpenAI API 调用或解析失败: {e}", exc_info=True)
            # Re-raise or return an error response
            raise
