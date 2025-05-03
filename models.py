from pydantic import BaseModel
from typing import Optional, Union

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

class Oops(OopsResponse):
    image_path: str = None  # 图片路径

class Request(BaseModel):
    image: bytes
    image_path: Optional[str]
    prompt: str

class AnalyzeError(BaseModel):
    level: str
    status: str
    reasons: str

# TODO: 错误信息
# class Response(BaseModel):
#     pass
Response = Union[OopsResponse, AnalyzeError]