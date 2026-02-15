from typing import Any, Protocol


class AIClient(Protocol):
    """Contract for low-level LLM chat capabilities.

    Domain-specific solve/tag logic must stay outside infrastructure clients.
    """

    model: str

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """Generic structured generation that returns a JSON-like dict."""

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """Structured generation that can also consume a single image."""
