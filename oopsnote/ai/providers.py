"""Provider profile metadata and explicit LangChain client construction."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from oopsnote.ai.secrets import SecretStore


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    base_url: HttpUrl
    credential_ref: str = Field(min_length=1, max_length=128)
    enabled: bool = True

    def public_view(self, secret_store: SecretStore) -> dict[str, Any]:
        value = self.model_dump(mode="json")
        value.pop("credential_ref")
        value["has_secret"] = secret_store.has(self.credential_ref)
        return value


class ProviderClientFactory:
    """The sole provider adapter boundary; no environment credential lookup."""

    def __init__(self, secret_store: SecretStore) -> None:
        self.secret_store = secret_store

    def create_chat_model(self, profile: ProviderProfile) -> Any:
        if not profile.enabled:
            raise ValueError("provider profile is disabled")
        api_key = self.secret_store.get(profile.credential_ref)
        provider = profile.provider.lower()
        if provider not in {"deepseek", "openai-compatible", "openai"}:
            raise ValueError(f"unsupported provider: {profile.provider}")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as error:
            raise RuntimeError("LangChain OpenAI integration is not installed") from error
        return ChatOpenAI(model=profile.model, base_url=str(profile.base_url), api_key=api_key)

    def validate(self, profile: ProviderProfile) -> dict[str, Any]:
        """Perform explicit provider connectivity validation before activation."""
        model = self.create_chat_model(profile)
        response = model.invoke("Reply with OK.")
        usage = getattr(response, "usage_metadata", None) or {}
        return {"ok": True, "usage": {key: usage.get(key) for key in ("input_tokens", "output_tokens") if usage.get(key) is not None}}


__all__ = ["ProviderClientFactory", "ProviderProfile"]
