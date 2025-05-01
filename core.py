from google import genai
from models import Response, Request

class Generate:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(self, request: Request) -> Response:
        """
        生成内容的函数，返回解析后的结果
        """
        client = genai.Client(api_key=self.api_key)

        contents = [
            genai.types.Part.from_bytes(
                data=request.image,
                mime_type='image/jpeg',
            ),
            genai.types.Content(
                role="user",
                parts=[
                    genai.types.Part.from_text(text="""特允许自定义标签"""),
                ],
            ),
        ]
        response = client.models.generate_content(
            model=self.model,
            contents=contents,
            config={
                'response_mime_type': 'application/json',
                'response_schema': Response,
                'system_instruction': [
                    genai.types.Part.from_text(text=request.prompt),
                ],
            },
        )
        return response.parsed
