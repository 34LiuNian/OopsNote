"""REST-only request DTOs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from oopsnote.core import TagDimension


class UploadRequest(BaseModel):
    subject: str = "auto"
    notes: str = ""
    question_no: Optional[str] = None
    source: Optional[str] = None
    question_type: Optional[str] = None
    difficulty: Optional[str] = None
    knowledge_tags: list[str] = Field(default_factory=list)
    error_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    image_base64: str
    filename: str
    mime_type: str = "image/png"
    batch_session_hash: Optional[str] = None
    batch_segment_id: Optional[str] = None
    batch_page_index: Optional[int] = Field(default=None, ge=0)
    batch_question_no: Optional[int] = Field(default=None, ge=1)


class TagInput(BaseModel):
    dimension: TagDimension
    value: str
    aliases: list[str] = Field(default_factory=list)
    subject: Optional[str] = None


class TagRenameInput(BaseModel):
    value: str


__all__ = ["TagInput", "TagRenameInput", "UploadRequest"]
