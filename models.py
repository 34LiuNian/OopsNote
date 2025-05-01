from pydantic import BaseModel
from typing import Optional, Union, List

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
    prompt: str | None

class AnalyzeError(BaseModel):
    level: str
    status: str
    reasons: str

Response = Union[OopsResponse, AnalyzeError]