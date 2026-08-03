"""Provider profile metadata and explicit LangChain client construction."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from oopsnote.ai.secrets import SecretNotFoundError, SecretStore
from oopsnote.core.models import RunStatus


SUPPORTED_PROVIDERS = frozenset({"deepseek", "openai", "anthropic", "google", "openai-compatible"})


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_calling: bool = True
    vision: bool = False


class ProviderValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    provider: str
    model: str
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    message: str
    tested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProviderConnectionError(RuntimeError):
    def __init__(self, result: ProviderValidationResult) -> None:
        super().__init__(result.message)
        self.result = result


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    display_name: str | None = Field(default=None, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    base_url: HttpUrl | None = None
    credential_ref: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool = True
    capability: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    secret_updated_at: datetime | None = None

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        normalized = value.strip().lower().replace("_", "-")
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported provider: {value}")
        return normalized

    def public_view(self, secret_store: SecretStore) -> dict[str, Any]:
        value = self.model_dump(mode="json")
        value.pop("credential_ref")
        value["display_name"] = self.display_name or self.id
        value["has_secret"] = secret_store.has(self.credential_ref)
        return value


class ProviderClientFactory:
    """The sole provider adapter boundary; no environment credential lookup."""

    def __init__(self, secret_store: SecretStore) -> None:
        self.secret_store = secret_store

    def create_chat_model(self, profile: ProviderProfile) -> Any:
        if not profile.enabled:
            raise ValueError("provider profile is disabled")
        if not profile.credential_ref:
            raise ValueError("provider profile has no credential")
        api_key = self.secret_store.get(profile.credential_ref)
        provider = profile.provider.lower()
        if provider == "deepseek":
            try:
                from langchain_deepseek import ChatDeepSeek
            except ImportError as error:
                raise RuntimeError("LangChain DeepSeek integration is not installed") from error
            return ChatDeepSeek(
                model=profile.model,
                api_key=api_key,
                base_url=str(profile.base_url or "https://api.deepseek.com/v1"),
                max_retries=0,
                timeout=60,
            )
        if provider in {"openai", "openai-compatible"}:
            if provider == "openai-compatible" and profile.base_url is None:
                raise ValueError("openai-compatible provider requires base_url")
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as error:
                raise RuntimeError("LangChain OpenAI integration is not installed") from error
            return ChatOpenAI(
                model=profile.model,
                base_url=str(profile.base_url) if profile.base_url else None,
                api_key=api_key,
                max_retries=0,
                timeout=60,
            )
        if provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError as error:
                raise RuntimeError("LangChain Anthropic integration is not installed") from error
            return ChatAnthropic(
                model=profile.model,
                api_key=api_key,
                max_retries=0,
                timeout=60,
            )
        if provider == "google":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as error:
                raise RuntimeError("LangChain Google integration is not installed") from error
            return ChatGoogleGenerativeAI(
                model=profile.model,
                api_key=api_key,
                vertexai=False,
                retries=0,
                request_timeout=60,
            )
        raise ValueError(f"unsupported provider: {profile.provider}")

    @staticmethod
    def _error_code(error: Exception) -> str:
        status = getattr(error, "status_code", None)
        if status is None:
            status = getattr(getattr(error, "response", None), "status_code", None)
        if status in {401, 403}:
            return "authentication_failed"
        if status == 429:
            return "rate_limited"
        if status in {500, 502, 503, 504}:
            return "provider_unavailable"
        if isinstance(error, (ConnectionError, TimeoutError)):
            return "connection_failed"
        if type(error).__name__ in {"APIConnectionError", "APITimeoutError"}:
            return "connection_failed"
        if isinstance(error, ValueError):
            return "invalid_configuration"
        return "validation_failed"

    def check(self, profile: ProviderProfile) -> ProviderValidationResult:
        """Make one explicit minimal call and return only stable, redacted evidence."""
        started = time.monotonic()
        try:
            model = self.create_chat_model(profile)
            model.invoke("Reply with OK.")
        except Exception as error:
            return ProviderValidationResult(
                success=False,
                provider=profile.provider,
                model=profile.model,
                latency_ms=max(0, round((time.monotonic() - started) * 1000)),
                error_code=self._error_code(error),
                message="Provider connection validation failed",
            )
        return ProviderValidationResult(
            success=True,
            provider=profile.provider,
            model=profile.model,
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            message="Connection validated",
        )

    def validate(self, profile: ProviderProfile) -> dict[str, Any]:
        """Validate connectivity or raise a redacted, classified error."""
        result = self.check(profile)
        if not result.success:
            raise ProviderConnectionError(result)
        return result.model_dump(mode="json")


def collect_unreferenced_profile_secrets(
    secret_store: SecretStore,
    profiles: Iterable[ProviderProfile],
    runs: Iterable[Any],
) -> int:
    """Delete historical refs only after no profile or active run retains them."""
    profile_references = {profile.credential_ref for profile in profiles if profile.credential_ref}
    historical_references: set[str] = set()
    active_references: set[str] = set()
    for run in runs:
        snapshot = getattr(run, "provider_profile_snapshot", None)
        if not isinstance(snapshot, dict):
            continue
        reference = snapshot.get("credential_ref")
        if not isinstance(reference, str) or not reference:
            continue
        historical_references.add(reference)
        if getattr(run, "status", None) in {RunStatus.QUEUED, RunStatus.RUNNING}:
            active_references.add(reference)
    deleted = 0
    for reference in historical_references - profile_references - active_references:
        try:
            secret_store.delete(reference)
        except SecretNotFoundError:
            continue
        deleted += 1
    return deleted


__all__ = [
    "ProviderCapabilities",
    "ProviderClientFactory",
    "ProviderConnectionError",
    "ProviderProfile",
    "ProviderValidationResult",
    "SUPPORTED_PROVIDERS",
    "collect_unreferenced_profile_secrets",
]
