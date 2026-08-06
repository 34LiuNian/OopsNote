"""Administrator-only provider channels, model catalogues, and LangChain policy."""

from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from oopsnote.ai.providers import (
    ChannelModel,
    LangChainModelPolicy,
    ProviderCapabilities,
    ProviderChannel,
    ProviderClientFactory,
    ProviderConnectionError,
    ProviderValidationResult,
    StageModelSelection,
    profile_for_channel_model,
)
from oopsnote.ai.secrets import SecretStoreCorruptionError
from oopsnote.api.auth import AuthenticationError, require_admin_request
from oopsnote.core import RunStatus

router = APIRouter(prefix="/settings/ai", tags=["ai-settings"])


class ChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    icon: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: HttpUrl | None = None
    enabled: bool = True


class ChannelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    icon: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: HttpUrl | None = None
    enabled: bool | None = None


class CredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=1, max_length=16_384)


class ModelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    capability: ProviderCapabilities | None = None


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vision: StageModelSelection
    agent: StageModelSelection
    review: StageModelSelection
    diagram: StageModelSelection


class RuntimeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrency: int = Field(ge=1, le=16)


class ChannelOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel_ids: list[str] = Field(min_length=0)


class ChannelCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=256)


def _api():
    from oopsnote.api import main

    return main


def _require_admin(request: Request) -> None:
    try:
        require_admin_request(request)
    except AuthenticationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def _vault():
    try:
        return _api().get_secret_store()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="provider secret store is unavailable") from error


def _channel(channel_id: str) -> ProviderChannel:
    channel = next((item for item in _api().APP_SETTINGS_STORE.provider_channels() if item.id == channel_id), None)
    if channel is None:
        raise HTTPException(status_code=404, detail="provider channel not found")
    return channel


def _active_snapshot_contains(snapshot: Any, *, channel_id: str | None = None, credential_ref: str | None = None) -> bool:
    if isinstance(snapshot, dict):
        if channel_id and snapshot.get("channel_id") == channel_id:
            return True
        if credential_ref and snapshot.get("credential_ref") == credential_ref:
            return True
        return any(_active_snapshot_contains(value, channel_id=channel_id, credential_ref=credential_ref) for value in snapshot.values())
    if isinstance(snapshot, list):
        return any(_active_snapshot_contains(value, channel_id=channel_id, credential_ref=credential_ref) for value in snapshot)
    return False


def _is_in_use(channel: ProviderChannel) -> bool:
    return any(
        _active_snapshot_contains(run.provider_profile_snapshot, channel_id=channel.id, credential_ref=channel.credential_ref)
        for run in _api().RUN_STORE.list_all()
        if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
    )


def _public(channel: ProviderChannel) -> dict[str, Any]:
    settings = _api().APP_SETTINGS_STORE.get()
    policy = _api().APP_SETTINGS_STORE.langchain_model_policy()
    try:
        value = channel.public_view(_vault())
    except SecretStoreCorruptionError as error:
        raise HTTPException(status_code=503, detail="provider secret store is unavailable") from error
    value["policy_stages"] = [
        stage for stage in ("vision", "agent", "review", "diagram")
        if policy is not None and getattr(policy, stage).channel_id == channel.id
    ]
    return value


def _merge_discovered_models(
    channel: ProviderChannel,
    discovered: list[ChannelModel],
) -> tuple[ChannelModel, ...]:
    """Keep administrator-confirmed capabilities when refreshing a catalogue."""

    existing = {item.id: item for item in channel.models}
    return tuple(
        item.model_copy(
            update={
                "enabled": existing[item.id].enabled,
                "capability": existing[item.id].capability,
            }
        )
        if item.id in existing
        else item
        for item in discovered
    )


def _catalog_validation(channel: ProviderChannel, started: float) -> ProviderValidationResult:
    """Return redacted evidence for the credential's explicit catalog check."""
    return ProviderValidationResult(
        success=True,
        provider=channel.provider,
        model="catalog",
        latency_ms=max(0, round((monotonic() - started) * 1000)),
        message="Credentials and model catalog validated",
    )


def _retire_legacy() -> None:
    """Delete retired Profile metadata and secrets unless an active run still references them."""
    api = _api()
    old_references = api.APP_SETTINGS_STORE.retire_legacy_provider_secrets()
    if not old_references:
        return
    vault = _vault()
    for credential_ref in old_references:
        if any(
            _active_snapshot_contains(run.provider_profile_snapshot, credential_ref=credential_ref)
            for run in api.RUN_STORE.list_all()
            if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
        ):
            continue
        try:
            vault.delete(credential_ref)
        except KeyError:
            pass


def retire_legacy_provider_configuration() -> None:
    """Run bounded startup migrations for legacy settings."""
    _api().APP_SETTINGS_STORE.migrate_legacy_diagram_policy()
    _retire_legacy()


@router.get("/channels")
def list_channels(request: Request) -> dict[str, Any]:
    _require_admin(request)
    _retire_legacy()
    api = _api()
    policy = api.APP_SETTINGS_STORE.langchain_model_policy()
    return {
        "items": [_public(channel) for channel in api.APP_SETTINGS_STORE.provider_channels()],
        "policy": policy.model_dump(mode="json") if policy else None,
    }


@router.post("/channels", status_code=201)
def create_channel(payload: ChannelCreate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    if any(item.id == payload.id for item in api.APP_SETTINGS_STORE.provider_channels()):
        raise HTTPException(status_code=409, detail="provider channel already exists")
    now = datetime.now(timezone.utc)
    channel = ProviderChannel(**payload.model_dump(), version=1, created_at=now, updated_at=now)
    api.APP_SETTINGS_STORE.upsert_provider_channel(channel)
    return {"channel": _public(channel)}


@router.patch("/channels/order")
def reorder_channels(payload: ChannelOrderUpdate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    try:
        _api().APP_SETTINGS_STORE.reorder_provider_channels(payload.channel_ids)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"items": [_public(channel) for channel in _api().APP_SETTINGS_STORE.provider_channels()]}


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: str, payload: ChannelPatch, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    previous = _channel(channel_id)
    updates = payload.model_dump(exclude_unset=True)
    candidate = ProviderChannel.model_validate({
        **previous.model_dump(mode="json"),
        **updates,
        "version": previous.version + 1,
        "updated_at": datetime.now(timezone.utc),
    })
    api.APP_SETTINGS_STORE.upsert_provider_channel(candidate)
    return {"channel": _public(candidate)}


@router.post("/channels/{channel_id}/credential")
def update_credential(channel_id: str, payload: CredentialUpdate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    vault = _vault()
    previous = _channel(channel_id)
    reference = vault.put(payload.secret)
    candidate = previous.model_copy(update={
        "version": previous.version + 1,
        "credential_ref": reference,
        "secret_updated_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    try:
        started = monotonic()
        models = ProviderClientFactory(vault).discover_models(candidate)
        validation = _catalog_validation(candidate, started)
        candidate = candidate.model_copy(update={"models": _merge_discovered_models(previous, models)})
        api.APP_SETTINGS_STORE.upsert_provider_channel(candidate)
    except ProviderConnectionError as error:
        vault.delete(reference)
        raise HTTPException(status_code=422 if error.result.error_code in {"authentication_failed", "invalid_configuration"} else 502, detail={"code": error.result.error_code, "message": error.result.message}) from error
    except Exception:
        vault.delete(reference)
        raise
    if previous.credential_ref and previous.credential_ref != reference and not _is_in_use(previous):
        try:
            vault.delete(previous.credential_ref)
        except KeyError:
            pass
    return {
        "channel": _public(candidate),
        "discovery": {"count": len(models), "capabilities_unknown": True},
        "validation": validation.model_dump(mode="json"),
    }


@router.get("/channels/{channel_id}/credential")
def reveal_credential(channel_id: str, request: Request, response: Response) -> dict[str, str]:
    """Reveal one credential to an authenticated administrator without caching it."""

    _require_admin(request)
    channel = _channel(channel_id)
    if not channel.credential_ref:
        raise HTTPException(status_code=404, detail="channel has no credential")
    try:
        secret = _vault().get(channel.credential_ref)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="channel credential is unavailable") from error
    except SecretStoreCorruptionError as error:
        raise HTTPException(status_code=503, detail="provider secret store is unavailable") from error
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {"secret": secret}


@router.post("/channels/{channel_id}/models/sync")
def sync_models(channel_id: str, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    channel = _channel(channel_id)
    if not channel.credential_ref or not _vault().has(channel.credential_ref):
        raise HTTPException(status_code=409, detail="channel has no credential")
    started = monotonic()
    discovered = ProviderClientFactory(_vault()).discover_models(channel)
    validation = _catalog_validation(channel, started)
    merged = _merge_discovered_models(channel, discovered)
    candidate = channel.model_copy(update={"version": channel.version + 1, "models": tuple(merged), "updated_at": datetime.now(timezone.utc)})
    api.APP_SETTINGS_STORE.upsert_provider_channel(candidate)
    return {
        "channel": _public(candidate),
        "discovery": {"count": len(merged), "capabilities_unknown": True},
        "validation": validation.model_dump(mode="json"),
    }


@router.post("/channels/{channel_id}/check")
def check_channel(channel_id: str, payload: ChannelCheckRequest, request: Request) -> dict[str, Any]:
    _require_admin(request)
    channel = _channel(channel_id)
    vault = _vault()
    if not channel.credential_ref or not vault.has(channel.credential_ref):
        raise HTTPException(status_code=409, detail="channel has no credential")
    try:
        profile = profile_for_channel_model(channel, payload.model_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="channel model not found") from error
    return {"validation": ProviderClientFactory(vault).check(profile).model_dump(mode="json")}


@router.patch("/channels/{channel_id}/models/{model_id}")
def update_model(channel_id: str, model_id: str, payload: ModelPatch, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    channel = _channel(channel_id)
    try:
        selected = channel.model(model_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="channel model not found") from error
    updates = payload.model_dump(exclude_unset=True)
    model = selected.model_copy(update=updates)
    models = tuple(model if item.id == model_id else item for item in channel.models)
    candidate = channel.model_copy(update={"version": channel.version + 1, "models": models, "updated_at": datetime.now(timezone.utc)})
    api.APP_SETTINGS_STORE.upsert_provider_channel(candidate)
    return {"channel": _public(candidate)}


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str, request: Request) -> dict[str, bool]:
    _require_admin(request)
    channel = _channel(channel_id)
    if _is_in_use(channel):
        raise HTTPException(status_code=409, detail="channel_in_use")
    _api().APP_SETTINGS_STORE.remove_provider_channel(channel.id)
    if channel.credential_ref:
        try:
            _vault().delete(channel.credential_ref)
        except KeyError:
            pass
    return {"deleted": True}


def _validate_policy(payload: PolicyUpdate) -> LangChainModelPolicy:
    api = _api()
    channels = {channel.id: channel for channel in api.APP_SETTINGS_STORE.provider_channels()}
    for stage, selection in (("vision", payload.vision), ("agent", payload.agent), ("review", payload.review), ("diagram", payload.diagram)):
        channel = channels.get(selection.channel_id)
        if channel is None or not channel.enabled or not channel.credential_ref or not _vault().has(channel.credential_ref):
            raise HTTPException(status_code=409, detail=f"{stage} channel is unavailable")
        try:
            model = channel.model(selection.model_id)
        except KeyError as error:
            raise HTTPException(status_code=409, detail=f"{stage} model is unavailable") from error
        if not model.enabled:
            raise HTTPException(status_code=409, detail=f"{stage} model is disabled")
        if stage in {"vision", "diagram"} and not model.capability.vision:
            raise HTTPException(status_code=409, detail=f"{stage} stage requires an enabled Vision model")
        if stage in {"agent", "review"} and not model.capability.tool_calling:
            raise HTTPException(status_code=409, detail=f"{stage} stage requires Tool Calling")
    previous = api.APP_SETTINGS_STORE.langchain_model_policy()
    return LangChainModelPolicy(
        version=(previous.version + 1 if previous else 1),
        vision=payload.vision,
        agent=payload.agent,
        review=payload.review,
        diagram=payload.diagram,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/policy")
def get_policy(request: Request) -> dict[str, Any]:
    _require_admin(request)
    value = _api().APP_SETTINGS_STORE.langchain_model_policy()
    return {"policy": value.model_dump(mode="json") if value else None}


@router.put("/policy")
def update_policy(payload: PolicyUpdate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    policy = _validate_policy(payload)
    _api().APP_SETTINGS_STORE.set_langchain_model_policy(policy)
    return {"policy": policy.model_dump(mode="json")}


@router.get("/runtime")
def get_runtime(request: Request) -> dict[str, int]:
    _require_admin(request)
    value = _api().APP_SETTINGS_STORE.get().get("ai_max_concurrency", 4)
    return {"max_concurrency": max(1, min(16, int(value)))}


@router.put("/runtime")
def update_runtime(payload: RuntimeUpdate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    _api().APP_SETTINGS_STORE.update({"ai_max_concurrency": payload.max_concurrency})
    return {"max_concurrency": payload.max_concurrency, "restart_required": True}


__all__ = ["retire_legacy_provider_configuration", "router"]
