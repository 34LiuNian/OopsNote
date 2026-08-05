"""Provider profile metadata and explicit LangChain client construction."""

from __future__ import annotations

import time
import hashlib
from datetime import datetime, timezone
from collections.abc import Collection
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from oopsnote.ai.secrets import SecretNotFoundError, SecretStore
from oopsnote.core.models import RunStatus


SUPPORTED_PROVIDERS = frozenset({"deepseek", "openai", "anthropic", "google", "openai-compatible"})


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_calling: bool = False
    vision: bool = False


class ChannelModel(BaseModel):
    """One model discovered through a channel, with admin-confirmed capabilities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=256)
    source: str = Field(default="其他", min_length=1, max_length=128)
    enabled: bool = False
    capability: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    discovered_at: datetime | None = None


class ProviderChannel(BaseModel):
    """One credential boundary and its provider-owned model catalogue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    base_url: HttpUrl | None = None
    credential_ref: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool = True
    models: tuple[ChannelModel, ...] = ()
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

    def model(self, model_id: str) -> ChannelModel:
        for item in self.models:
            if item.id == model_id:
                return item
        raise KeyError(model_id)

    def public_view(self, secret_store: SecretStore) -> dict[str, Any]:
        value = self.model_dump(mode="json")
        value.pop("credential_ref")
        value["has_secret"] = secret_store.has(self.credential_ref)
        return value


class StageModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    channel_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)


class LangChainModelPolicy(BaseModel):
    """The only mutable selection authority for new LangChain runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    vision: StageModelSelection
    agent: StageModelSelection
    review: StageModelSelection
    updated_at: datetime | None = None


def profile_for_channel_model(channel: ProviderChannel, model_id: str) -> "ProviderProfile":
    """Adapt a selected channel model to the existing provider client boundary."""
    item = channel.model(model_id)
    stable_model_key = hashlib.sha256(item.id.encode("utf-8")).hexdigest()[:16]
    return ProviderProfile(
        id=f"{channel.id}:{stable_model_key}",
        version=channel.version,
        channel_id=channel.id,
        display_name=channel.display_name,
        provider=channel.provider,
        model=item.id,
        base_url=channel.base_url,
        credential_ref=channel.credential_ref,
        enabled=channel.enabled and item.enabled,
        capability=item.capability,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        secret_updated_at=channel.secret_updated_at,
    )


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
    channel_id: str | None = Field(default=None, max_length=128)
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
    """The sole provider adapter boundary; no environment credential lookup.

    ManagedAiRunner owns run cancellation and the deadline for the complete
    model/tool loop. Provider clients therefore disable SDK retries but do not
    impose a competing per-request deadline.
    """

    def __init__(self, secret_store: SecretStore) -> None:
        self.secret_store = secret_store

    @staticmethod
    def _is_dashscope_compatible(profile: ProviderProfile) -> bool:
        """Return whether an OpenAI adapter targets DashScope's compatible API."""

        if profile.provider not in {"openai", "openai-compatible"} or profile.base_url is None:
            return False
        host = (str(profile.base_url).split("/", 3)[2]).lower()
        return host == "dashscope.aliyuncs.com" or host.endswith(".maas.aliyuncs.com")

    @classmethod
    def _uses_managed_non_thinking_mode(cls, profile: ProviderProfile) -> bool:
        """Whether this provider needs non-thinking mode for a strict tool loop."""

        return (
            (profile.provider == "deepseek" and profile.model.startswith("deepseek-v4-"))
            or cls._is_dashscope_compatible(profile)
        )

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
            kwargs: dict[str, Any] = {
                "model": profile.model,
                "api_key": api_key,
                "base_url": str(profile.base_url or "https://api.deepseek.com/v1"),
                "max_retries": 0,
            }
            if self._uses_managed_non_thinking_mode(profile):
                # DeepSeek V4 thinking mode requires replaying provider-specific
                # reasoning content with every tool result. The managed loop
                # owns only canonical messages, so select the documented
                # non-thinking mode instead.
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
                kwargs["temperature"] = 0
                # Candidate/finalize tools carry an OopsMark JSON string. The
                # provider's default output cap can truncate that argument
                # before its closing JSON delimiter, which LangChain correctly
                # treats as an invalid tool call. This is a request-size limit,
                # not a lifecycle timeout or retry policy.
                kwargs["max_tokens"] = 8192
            return ChatDeepSeek(**kwargs)
        if provider in {"openai", "openai-compatible"}:
            if provider == "openai-compatible" and profile.base_url is None:
                raise ValueError("openai-compatible provider requires base_url")
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as error:
                raise RuntimeError("LangChain OpenAI integration is not installed") from error
            kwargs: dict[str, Any] = {
                "model": profile.model,
                "base_url": str(profile.base_url) if profile.base_url else None,
                "api_key": api_key,
                "max_retries": 0,
            }
            if self._is_dashscope_compatible(profile):
                # DashScope Qwen thinking mode rejects required tool choice and
                # may emit prose after a long tool history. Tool-driven OopsNote
                # stages need the provider's non-thinking mode.
                kwargs["extra_body"] = {"enable_thinking": False}
            return ChatOpenAI(
                **kwargs,
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
            )
        raise ValueError(f"unsupported provider: {profile.provider}")

    def bind_managed_tools(
        self,
        model: Any,
        profile: ProviderProfile,
        *,
        tool_names: Collection[str] | None = None,
        constants: dict[str, dict[str, Any]] | None = None,
        required_arguments: dict[str, Collection[str]] | None = None,
        parameter_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
    ) -> Any:
        """Bind phase-legal canonical tools with provider loop constraints."""

        from oopsnote.ai.langchain_tools import langchain_tool_schemas

        kwargs: dict[str, Any] = {}
        if self._uses_managed_non_thinking_mode(profile):
            # Required calls are valid once thinking mode is disabled. Every
            # managed turn must either call a pipeline tool or reach a
            # lifecycle-owned terminal state; prose cannot complete a run.
            kwargs = {"tool_choice": "required", "parallel_tool_calls": False}
        return model.bind_tools(
            langchain_tool_schemas(
                tool_names,
                constants=constants,
                required_arguments=required_arguments,
                parameter_overrides=parameter_overrides,
            ),
            **kwargs,
        )

    def create_vision_ocr_model(self, profile: ProviderProfile) -> Any:
        """Build a Vision model with the provider's native JSON-output mode.

        OCR is a structured extraction boundary. OpenAI-compatible providers
        expose a JSON-object response mode, which prevents otherwise valid
        prompts from intermittently producing Markdown or invalid escapes.
        Other provider adapters keep their documented default response mode.
        """

        model = self.create_chat_model(profile)
        if profile.provider in {"deepseek", "openai", "openai-compatible"}:
            return model.bind(
                response_format={"type": "json_object"},
                temperature=0,
            )
        return model

    @staticmethod
    def _catalog_url(channel: ProviderChannel) -> str:
        base_url = str(channel.base_url or "").rstrip("/")
        if channel.provider == "deepseek":
            return f"{base_url or 'https://api.deepseek.com/v1'}/models"
        if channel.provider in {"openai", "openai-compatible"}:
            if not base_url:
                base_url = "https://api.openai.com/v1"
            return f"{base_url}/models"
        if channel.provider == "anthropic":
            return f"{base_url or 'https://api.anthropic.com'}/v1/models"
        if channel.provider == "google":
            return f"{base_url or 'https://generativelanguage.googleapis.com'}/v1beta/models"
        raise ValueError(f"unsupported provider: {channel.provider}")

    def discover_models(self, channel: ProviderChannel) -> list[ChannelModel]:
        """Read the provider model catalogue without persisting secrets or guessing capabilities."""
        if not channel.credential_ref:
            raise ValueError("channel has no credential")
        if not channel.enabled:
            raise ValueError("channel is disabled")
        try:
            import httpx
        except ImportError as error:
            raise RuntimeError("httpx is required for provider model discovery") from error
        secret = self.secret_store.get(channel.credential_ref)
        headers: dict[str, str] = {}
        params: dict[str, str] = {}
        if channel.provider == "google":
            params["key"] = secret
        elif channel.provider == "anthropic":
            headers = {"x-api-key": secret, "anthropic-version": "2023-06-01"}
        else:
            headers = {"Authorization": f"Bearer {secret}"}
        try:
            response = httpx.get(self._catalog_url(channel), headers=headers, params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            result = ProviderValidationResult(
                success=False,
                provider=channel.provider,
                model="catalog",
                error_code=self._error_code(error),
                message="Provider model discovery failed",
            )
            raise ProviderConnectionError(result) from error
        raw_items = payload.get("models") if channel.provider == "google" else payload.get("data")
        if not isinstance(raw_items, list):
            raise ProviderConnectionError(ProviderValidationResult(
                success=False,
                provider=channel.provider,
                model="catalog",
                error_code="validation_failed",
                message="Provider model discovery returned an invalid catalogue",
            ))
        discovered_at = datetime.now(timezone.utc)
        items: list[ChannelModel] = []
        seen: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            model_id = raw.get("id") or raw.get("name")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            model_id = model_id.removeprefix("models/")
            if model_id in seen:
                continue
            seen.add(model_id)
            source = raw.get("owned_by") or raw.get("display_name") or channel.display_name
            items.append(ChannelModel(
                id=model_id,
                source=str(source).strip() or channel.display_name,
                # Provider catalogues do not consistently publish tool/vision support.
                # Unknown capabilities are deliberately closed until an admin confirms them.
                capability=ProviderCapabilities(),
                discovered_at=discovered_at,
            ))
        if not items:
            raise ProviderConnectionError(ProviderValidationResult(
                success=False,
                provider=channel.provider,
                model="catalog",
                error_code="validation_failed",
                message="Provider model discovery returned no usable models",
            ))
        return items

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


def collect_unreferenced_channel_secrets(
    secret_store: SecretStore,
    configured_channels: Iterable[Any],
    runs: Iterable[Any],
) -> int:
    """Delete historical refs only after no configured channel or active run retains them."""
    configured_references = {
        reference
        for item in configured_channels
        for reference in [getattr(item, "credential_ref", None)]
        if isinstance(reference, str) and reference
    }
    historical_references: set[str] = set()
    active_references: set[str] = set()

    def credential_refs(value: Any) -> set[str]:
        if isinstance(value, dict):
            refs = {value["credential_ref"]} if isinstance(value.get("credential_ref"), str) and value["credential_ref"] else set()
            for child in value.values():
                refs.update(credential_refs(child))
            return refs
        if isinstance(value, list):
            refs: set[str] = set()
            for child in value:
                refs.update(credential_refs(child))
            return refs
        return set()

    for run in runs:
        snapshot = getattr(run, "provider_profile_snapshot", None)
        if not isinstance(snapshot, dict):
            continue
        references = credential_refs(snapshot)
        historical_references.update(references)
        if getattr(run, "status", None) in {RunStatus.QUEUED, RunStatus.RUNNING}:
            active_references.update(references)
    deleted = 0
    for reference in historical_references - configured_references - active_references:
        try:
            secret_store.delete(reference)
        except SecretNotFoundError:
            continue
        deleted += 1
    return deleted


__all__ = [
    "ChannelModel",
    "LangChainModelPolicy",
    "ProviderCapabilities",
    "ProviderChannel",
    "ProviderClientFactory",
    "ProviderConnectionError",
    "ProviderProfile",
    "ProviderValidationResult",
    "SUPPORTED_PROVIDERS",
    "StageModelSelection",
    "collect_unreferenced_channel_secrets",
    "profile_for_channel_model",
]
