"""Administrator-only AI provider profiles, credentials, and runtime settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from oopsnote.ai.providers import (
    ProviderCapabilities,
    ProviderClientFactory,
    ProviderConnectionError,
    ProviderProfile,
)
from oopsnote.api.auth import AuthenticationError, require_admin_request
from oopsnote.core import RunStatus
from oopsnote.mcp.ocr import clear_ocr_vault, configure_ocr_vault

router = APIRouter(prefix="/settings/ai", tags=["ai-settings"])


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    base_url: HttpUrl | None = None
    enabled: bool = True
    capability: ProviderCapabilities = Field(default_factory=ProviderCapabilities)


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    base_url: HttpUrl | None = None
    enabled: bool | None = None
    capability: ProviderCapabilities | None = None


class CredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=1, max_length=16_384)


class ProfileSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=128)


class RuntimeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrency: int = Field(ge=1, le=16)


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


def _profile(profile_id: str) -> ProviderProfile:
    profile = next(
        (item for item in _api().APP_SETTINGS_STORE.provider_profiles() if item.id == profile_id),
        None,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="provider profile not found")
    return profile


def _active_snapshots() -> list[dict[str, Any]]:
    return [
        snapshot
        for run in _api().RUN_STORE.list_all()
        if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
        for snapshot in [run.provider_profile_snapshot]
        if isinstance(snapshot, dict)
    ]


def _is_in_use(profile: ProviderProfile) -> bool:
    return any(
        snapshot.get("id") == profile.id
        or (
            profile.credential_ref is not None
            and snapshot.get("credential_ref") == profile.credential_ref
        )
        for snapshot in _active_snapshots()
    )


def _public(profile: ProviderProfile) -> dict[str, Any]:
    api = _api()
    settings = api.APP_SETTINGS_STORE.get()
    return {
        **profile.public_view(_vault()),
        "is_default": settings.get("ai_provider_profile_id") == profile.id,
        "is_ocr": settings.get("ocr_profile_id") == profile.id,
        "validation": api.APP_SETTINGS_STORE.provider_validation(profile.id, profile.version),
    }


@router.get("/profiles")
def list_profiles(request: Request) -> dict[str, list[dict[str, Any]]]:
    _require_admin(request)
    return {"items": [_public(profile) for profile in _api().APP_SETTINGS_STORE.provider_profiles()]}


@router.post("/profiles", status_code=201)
def create_profile(payload: ProfileCreate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    if any(item.id == payload.id for item in api.APP_SETTINGS_STORE.provider_profiles()):
        raise HTTPException(status_code=409, detail="provider profile already exists")
    now = datetime.now(timezone.utc)
    profile = ProviderProfile(
        **payload.model_dump(),
        version=1,
        created_at=now,
        updated_at=now,
    )
    api.APP_SETTINGS_STORE.upsert_provider_profile(profile)
    return {"profile": _public(profile)}


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: str, payload: ProfilePatch, request: Request) -> dict[str, Any]:
    _require_admin(request)
    previous = _profile(profile_id)
    updates = payload.model_dump(exclude_unset=True)
    candidate = ProviderProfile.model_validate({
        **previous.model_dump(mode="json"),
        **updates,
        "version": previous.version + 1,
        "updated_at": datetime.now(timezone.utc),
    })
    settings = _api().APP_SETTINGS_STORE.get()
    if settings.get("ocr_profile_id") == candidate.id:
        if not candidate.credential_ref or candidate.base_url is None:
            raise HTTPException(status_code=409, detail="active OCR profile requires endpoint and credential")
    _api().APP_SETTINGS_STORE.upsert_provider_profile(candidate)
    if settings.get("ocr_profile_id") == candidate.id:
        configure_ocr_vault(
            _vault(), candidate.credential_ref, model=candidate.model, endpoint=str(candidate.base_url)
        )
    return {"profile": _public(candidate)}


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str, request: Request) -> dict[str, bool]:
    _require_admin(request)
    api = _api()
    profile = _profile(profile_id)
    if _is_in_use(profile):
        raise HTTPException(status_code=409, detail="profile_in_use")
    settings = api.APP_SETTINGS_STORE.get()
    if settings.get("ai_provider_profile_id") == profile.id or settings.get("ocr_profile_id") == profile.id:
        raise HTTPException(status_code=409, detail="profile_selected")
    api.APP_SETTINGS_STORE.remove_provider_profile(profile.id)
    if profile.credential_ref:
        try:
            _vault().delete(profile.credential_ref)
        except KeyError:
            pass
    return {"deleted": True}


@router.post("/profiles/{profile_id}/credential")
def update_credential(profile_id: str, payload: CredentialUpdate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    vault = _vault()
    previous = _profile(profile_id)
    reference = vault.put(payload.secret)
    now = datetime.now(timezone.utc)
    candidate = previous.model_copy(update={
        "version": previous.version + 1,
        "credential_ref": reference,
        "secret_updated_at": now,
        "updated_at": now,
    })
    factory = ProviderClientFactory(vault)
    try:
        result = factory.check(candidate)
        if not result.success:
            raise ProviderConnectionError(result)
        selected_for_ocr = api.APP_SETTINGS_STORE.get().get("ocr_profile_id") == candidate.id
        if selected_for_ocr and candidate.base_url is None:
            raise ValueError("OCR profile requires base_url")
        api.APP_SETTINGS_STORE.commit_validated_provider_profile(
            candidate,
            result,
            select_if_unset=True,
        )
        if selected_for_ocr:
            configure_ocr_vault(vault, reference, model=candidate.model, endpoint=str(candidate.base_url))
    except ProviderConnectionError as error:
        vault.delete(reference)
        raise HTTPException(
            status_code=422 if error.result.error_code in {"authentication_failed", "invalid_configuration"} else 502,
            detail={"code": error.result.error_code, "message": error.result.message, "validation": error.result.model_dump(mode="json")},
        ) from error
    except Exception:
        vault.delete(reference)
        raise
    if previous.credential_ref and previous.credential_ref != reference and not _is_in_use(previous):
        try:
            vault.delete(previous.credential_ref)
        except KeyError:
            pass
    return {"profile": _public(candidate), "validation": result.model_dump(mode="json")}


@router.delete("/profiles/{profile_id}/credential")
def delete_credential(profile_id: str, request: Request) -> dict[str, Any]:
    _require_admin(request)
    profile = _profile(profile_id)
    if _is_in_use(profile):
        raise HTTPException(status_code=409, detail="profile_in_use")
    if not profile.credential_ref:
        return {"profile": _public(profile)}
    candidate = profile.model_copy(update={
        "version": profile.version + 1,
        "credential_ref": None,
        "secret_updated_at": None,
        "updated_at": datetime.now(timezone.utc),
    })
    was_ocr = _api().APP_SETTINGS_STORE.get().get("ocr_profile_id") == profile.id
    _api().APP_SETTINGS_STORE.clear_provider_credential(candidate)
    _vault().delete(profile.credential_ref)
    if was_ocr:
        clear_ocr_vault()
    return {"profile": _public(candidate)}


@router.post("/profiles/{profile_id}/test")
def test_profile(profile_id: str, request: Request) -> dict[str, Any]:
    _require_admin(request)
    profile = _profile(profile_id)
    result = ProviderClientFactory(_vault()).check(profile)
    _api().APP_SETTINGS_STORE.record_provider_validation(profile.id, profile.version, result)
    return {"validation": result.model_dump(mode="json")}


@router.put("/default-profile")
def select_default(payload: ProfileSelection, request: Request) -> dict[str, Any]:
    _require_admin(request)
    profile = _profile(payload.profile_id)
    if not profile.enabled or not _vault().has(profile.credential_ref):
        raise HTTPException(status_code=409, detail="profile is disabled or has no credential")
    _api().APP_SETTINGS_STORE.update({"ai_provider_profile_id": profile.id})
    return {"profile_id": profile.id, "version": profile.version}


@router.put("/ocr-profile")
def select_ocr(payload: ProfileSelection, request: Request) -> dict[str, Any]:
    _require_admin(request)
    profile = _profile(payload.profile_id)
    if not profile.enabled or not profile.credential_ref or profile.base_url is None:
        raise HTTPException(status_code=409, detail="OCR profile requires endpoint and credential")
    if not _vault().has(profile.credential_ref):
        raise HTTPException(status_code=409, detail="OCR profile has no credential")
    _api().APP_SETTINGS_STORE.update({"ocr_profile_id": profile.id})
    configure_ocr_vault(_vault(), profile.credential_ref, model=profile.model, endpoint=str(profile.base_url))
    return {"profile_id": profile.id, "version": profile.version}


@router.get("/runtime")
def get_runtime(request: Request) -> dict[str, int]:
    _require_admin(request)
    value = _api().APP_SETTINGS_STORE.get().get("ai_max_concurrency", 1)
    return {"max_concurrency": max(1, min(16, int(value)))}


@router.put("/runtime")
def update_runtime(payload: RuntimeUpdate, request: Request) -> dict[str, Any]:
    _require_admin(request)
    _api().APP_SETTINGS_STORE.update({"ai_max_concurrency": payload.max_concurrency})
    return {"max_concurrency": payload.max_concurrency, "restart_required": True}


__all__ = ["router"]
