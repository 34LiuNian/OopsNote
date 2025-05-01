from models import Response, Request
from pydantic import TypeAdapter
from google import genai
from logger import logging
import openai
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
        self.client = genai.Client(api_key=self.api_key)
        logger.info("生成器初始化完成。")
    
    
    def generate(self, request: Request) -> Response:
        """
        匹配生成模式
        """
        if self.mode == "GEMINI":
            return self.gemini_generate(request)
        elif self.mode == "OPENAI":
            return self.openai_compatible_generate(request) # TODO: Qwen3 生成


    def gemini_generate(self, request: Request) -> Response:
        """
        gemini实现
        """
        

        contents = [
            genai.types.Part.from_bytes(
                data=request.image,
                mime_type='image/jpeg',
            ),
            genai.types.Content(
                role="user",
                parts=[
                    genai.types.Part.from_text(text=request.prompt),
                ],
            ),
        ]
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config={
                'response_mime_type': 'application/json',
                'response_schema': Response,
                'system_instruction': [
                    genai.types.Part.from_text(text=self.system_instruction),
                ],
            },
        )
        return response.parsed
    
    
    def openai_compatible_generate(self, request: Request) -> Response:
        """
        OpenAI 实现
        """
        
        
        base64_image_url = f"data:image/jpeg;base64,{request.image}"

        messages = [
            {"role": "system", "content": self.system_instruction},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": base64_image_url,
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": request.prompt,
                    },
                ],
            },
        ]

        response = openai.ChatCompletion.create(
            model=self.model,
            messages=messages,
            temperature=self.tempterature,
            response_format="json",
        )

        # 自动解析成 Response 类型（你定义的）
        json_data = response.choices[0].message.function_call.arguments
        parsed = TypeAdapter(Response).validate_json(json_data)
        return parsed
