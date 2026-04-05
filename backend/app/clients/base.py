from typing import Any, Protocol


class AIClient(Protocol):
    """底层 LLM 对话能力协议。

    领域层的解题/打标逻辑必须留在客户端之外。
    """

    model: str

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """通用结构化生成，返回 JSON 风格字典。"""

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """支持单图输入的结构化生成接口。"""
