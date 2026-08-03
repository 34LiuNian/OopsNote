"""Problem search, tag, settings, and synchronization routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from oopsnote.api.schemas import TagInput, TagRenameInput
from oopsnote.api.auth import AuthenticationError, require_admin_request
from oopsnote.ai.providers import ProviderClientFactory, ProviderProfile
from oopsnote.core import Problem, Searcher, SearchQuery, TagDimension, TagItem
from oopsnote.core import RunStatus
from oopsnote.mcp.ocr import configure_ocr_vault
from oopsnote.obsidian.syncer import ObsidianSyncer

router = APIRouter()

class PiConcurrencyUpdate(BaseModel):
    pi_concurrency: int = Field(ge=1, le=16)


def _api():
    from oopsnote.api import main

    return main


def _require_admin(request: Request) -> None:
    try:
        require_admin_request(request)
    except AuthenticationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.get("/settings/provider-profiles")
def list_provider_profiles(request: Request) -> dict[str, list[dict[str, Any]]]:
    _require_admin(request)
    api = _api()
    try:
        secret_store = api.get_secret_store()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="provider secret store is unavailable") from error
    settings = api.APP_SETTINGS_STORE.get()
    return {
        "items": [
            {
                **profile.model_dump(mode="json", exclude={"credential_ref"}),
                "has_secret": secret_store.has(profile.credential_ref),
                "active": settings.get("ai_provider_profile_id") == profile.id,
                "ocr_active": settings.get("ocr_profile_id") == profile.id,
            }
            for profile in api.APP_SETTINGS_STORE.provider_profiles()
        ]
    }


@router.post("/settings/provider-profiles")
def create_provider_profile(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Create and validate a profile without exposing its credential reference."""
    api = _api()
    _require_admin(request)
    secret = payload.get("secret")
    if not isinstance(secret, str) or not secret:
        raise HTTPException(status_code=422, detail="secret is required")
    if "credential_ref" in payload:
        raise HTTPException(status_code=422, detail="credential_ref is server-managed")
    try:
        vault = api.get_secret_store()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="provider secret store is unavailable") from error
    try:
        reference = vault.put(secret)
        profile = ProviderProfile.model_validate({
            **{key: value for key, value in payload.items() if key != "secret"},
            "version": int(payload.get("version", 1)),
            "credential_ref": reference,
        })
        ProviderClientFactory(vault).validate(profile)
        api.APP_SETTINGS_STORE.upsert_provider_profile(profile, select_if_unset=True)
    except ValueError as error:
        if "reference" in locals():
            try: vault.delete(reference)
            except Exception: pass
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        if "reference" in locals():
            try: vault.delete(reference)
            except Exception: pass
        raise HTTPException(status_code=502, detail="provider validation failed") from error
    return {"profile": {**profile.model_dump(mode="json", exclude={"credential_ref"}), "has_secret": True}, "validation": {"ok": True}}


@router.post("/settings/provider-profiles/{profile_id}/activate")
def activate_provider_profile(profile_id: str, request: Request) -> dict[str, Any]:
    """Select one enabled, vault-backed profile for newly admitted runs."""
    api = _api()
    _require_admin(request)
    profile = next((item for item in api.APP_SETTINGS_STORE.provider_profiles() if item.id == profile_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="provider profile not found")
    if not profile.enabled:
        raise HTTPException(status_code=409, detail="provider profile is disabled")
    try:
        if not api.get_secret_store().has(profile.credential_ref):
            raise HTTPException(status_code=409, detail="provider profile has no secret")
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    api.APP_SETTINGS_STORE.update({"ai_provider_profile_id": profile.id})
    return {"profile_id": profile.id, "version": profile.version, "active": True}


@router.post("/settings/ocr-profile")
def activate_ocr_profile(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Select the vault-backed OCR profile used by future LangChain runs."""
    api = _api()
    _require_admin(request)
    profile_id = payload.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        raise HTTPException(status_code=422, detail="profile_id is required")
    profile = next((item for item in api.APP_SETTINGS_STORE.provider_profiles() if item.id == profile_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="provider profile not found")
    if not profile.enabled:
        raise HTTPException(status_code=409, detail="provider profile is disabled")
    try:
        if not api.get_secret_store().has(profile.credential_ref):
            raise HTTPException(status_code=409, detail="OCR profile has no secret")
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    api.APP_SETTINGS_STORE.update({"ocr_profile_id": profile.id})
    configure_ocr_vault(
        api.get_secret_store(),
        profile.credential_ref,
        model=profile.model,
        endpoint=str(profile.base_url),
    )
    return {"profile_id": profile.id, "version": profile.version, "active": True}


@router.post("/settings/provider-profiles/{profile_id}/secret")
def rotate_provider_secret(profile_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Validate a new secret, atomically activate its profile version, then retire old ref."""
    api = _api()
    _require_admin(request)
    secret = payload.get("secret")
    if not isinstance(secret, str) or not secret:
        raise HTTPException(status_code=422, detail="secret is required")
    try:
        vault = api.get_secret_store()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    profiles = {profile.id: profile for profile in api.APP_SETTINGS_STORE.provider_profiles()}
    previous = profiles.get(profile_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="provider profile not found")
    reference = vault.put(secret)
    updates = {
        key: payload[key]
        for key in ("provider", "model", "base_url", "enabled")
        if key in payload
    }
    try:
        candidate = ProviderProfile.model_validate({
            **previous.model_dump(mode="json"),
            **updates,
            "version": previous.version + 1,
            "credential_ref": reference,
        })
    except ValueError as error:
        vault.delete(reference)
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        ProviderClientFactory(vault).validate(candidate)
        api.APP_SETTINGS_STORE.upsert_provider_profile(candidate)
        if api.APP_SETTINGS_STORE.get().get("ocr_profile_id") == candidate.id:
            configure_ocr_vault(
                vault,
                candidate.credential_ref,
                model=candidate.model,
                endpoint=str(candidate.base_url),
            )
    except Exception as error:
        try:
            vault.delete(reference)
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="provider validation failed") from error
    active_references = {
        snapshot.get("credential_ref")
        for run in api.RUN_STORE.list_all()
        if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
        for snapshot in [run.provider_profile_snapshot]
        if isinstance(snapshot, dict)
    }
    if previous.credential_ref != reference and previous.credential_ref not in active_references:
        try:
            vault.delete(previous.credential_ref)
        except Exception:
            pass
    return {"profile": {**candidate.model_dump(mode="json", exclude={"credential_ref"}), "has_secret": True}, "validation": {"ok": True}}


def _tag_reference_count(dimension: TagDimension, value: str) -> int:
    count = 0
    api = _api()
    for task in api.TASK_STORE.list_all():
        problem = task.problem
        if dimension == TagDimension.KNOWLEDGE and problem:
            count += problem.knowledge_points.count(value)
        elif dimension == TagDimension.ERROR and problem:
            count += problem.error_hypothesis.count(value)
        elif dimension == TagDimension.CUSTOM:
            count += list(task.metadata.get("user_tags") or []).count(value)
        elif dimension == TagDimension.META:
            source = api._problem_source(task, problem) if problem else task.metadata.get("source")
            if source == value:
                count += 1
    return count


def _tag_reference_counts() -> dict[tuple[TagDimension, str], int]:
    counts: dict[tuple[TagDimension, str], int] = {}
    api = _api()
    for task in api.TASK_STORE.list_all():
        problem = task.problem
        values: list[tuple[TagDimension, str]] = []
        if problem:
            values.extend((TagDimension.KNOWLEDGE, value) for value in problem.knowledge_points)
            values.extend((TagDimension.ERROR, value) for value in problem.error_hypothesis)
            source = api._problem_source(task, problem)
            if source:
                values.append((TagDimension.META, source))
        values.extend((TagDimension.CUSTOM, value) for value in task.metadata.get("user_tags", []))
        metadata_source = task.metadata.get("source")
        if metadata_source and not problem:
            values.append((TagDimension.META, metadata_source))
        for key in values:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _source_tag_items(
    query: Optional[str],
    subject: Optional[str],
    limit: int,
) -> list[TagItem]:
    """Project document-level sources from tasks; page location lives in source_page/trace."""
    api = _api()
    normalized_query = (query or "").strip().casefold()
    counts: dict[str, int] = {}
    for task in api.TASK_STORE.list_all():
        problem = task.problem
        if not problem:
            continue
        if subject and (problem.subject or task.subject) != subject:
            continue
        source = api._problem_source(task, problem)
        if not source or (normalized_query and normalized_query not in source.casefold()):
            continue
        counts[source] = counts.get(source, 0) + 1
    return [
        TagItem(
            id=uuid5(NAMESPACE_URL, f"oopsnote-source:{value}").hex,
            dimension=TagDimension.META,
            value=value,
            ref_count=count,
            source="derived",
        )
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:limit]
    ]


def _replace_tag_references(
    dimension: TagDimension,
    old_value: str,
    new_value: str,
) -> tuple[int, int]:
    tasks_modified = 0
    fields_modified = 0
    api = _api()
    for task in api.TASK_STORE.list_all():
        problem = task.problem
        metadata = dict(task.metadata)
        next_problem = problem
        changed_fields = 0
        if problem and dimension == TagDimension.KNOWLEDGE and old_value in problem.knowledge_points:
            values = [new_value if value == old_value else value for value in problem.knowledge_points]
            next_problem = problem.model_copy(update={"knowledge_points": list(dict.fromkeys(values))})
            changed_fields += 1
        elif problem and dimension == TagDimension.ERROR and old_value in problem.error_hypothesis:
            values = [new_value if value == old_value else value for value in problem.error_hypothesis]
            next_problem = problem.model_copy(update={"error_hypothesis": list(dict.fromkeys(values))})
            changed_fields += 1
        elif dimension == TagDimension.CUSTOM and old_value in list(metadata.get("user_tags") or []):
            values = [new_value if value == old_value else value for value in metadata.get("user_tags", [])]
            metadata["user_tags"] = list(dict.fromkeys(values))
            changed_fields += 1
        elif dimension == TagDimension.META:
            if metadata.get("source") == old_value:
                metadata["source"] = new_value
                changed_fields += 1
            if problem and problem.source == old_value:
                next_problem = problem.model_copy(update={"source": new_value})
                changed_fields += 1
        if changed_fields:
            api.TASK_STORE.update(task.id, problem=next_problem, metadata=metadata)
            tasks_modified += 1
            fields_modified += changed_fields
    return tasks_modified, fields_modified

@router.get("/settings/pi")
def get_pi_settings() -> dict[str, Any]:
    api = _api()
    configured = int(api.APP_SETTINGS_STORE.get().get("pi_concurrency", 3))
    return {
        "pi_concurrency": api.PI_RUNNER.max_concurrent_tasks if api.PI_RUNNER else configured,
        "workers": api.PI_RUNNER.dispatcher_status()["workers"] if api.PI_RUNNER else 0,
        "enabled": api.PI_RUNNER is not None,
        "applies_on_restart": True,
    }

@router.put("/settings/pi")
def update_pi_settings(payload: PiConcurrencyUpdate) -> dict[str, Any]:
    api = _api()
    api.APP_SETTINGS_STORE.update({"pi_concurrency": payload.pi_concurrency})
    return {
        "pi_concurrency": payload.pi_concurrency,
        "workers": api.PI_RUNNER.dispatcher_status()["workers"] if api.PI_RUNNER else 0,
        "enabled": api.PI_RUNNER is not None,
        "applies_on_restart": True,
    }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid ISO datetime")


@router.get("/problems")
def list_problems(
    subject: Optional[str] = None,
    source: Optional[list[str]] = Query(default=None),
    knowledge_tag: Optional[list[str]] = Query(default=None),
    error_tag: Optional[list[str]] = Query(default=None),
    user_tag: Optional[list[str]] = Query(default=None),
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    after = _parse_iso(created_after)
    before = _parse_iso(created_before)
    items: list[dict[str, Any]] = []
    for task in api.TASK_STORE.list_all():
        problem = task.problem
        if not problem:
            continue
        item = api._problem_summary(task, problem)
        if subject and item["subject"] != subject:
            continue
        if source and item["source"] not in source:
            continue
        if knowledge_tag and not set(knowledge_tag).issubset(
            item["knowledge_tags"]
        ):
            continue
        if error_tag and not set(error_tag).issubset(item["error_tags"]):
            continue
        if user_tag and not set(user_tag).issubset(item["user_tags"]):
            continue
        created = problem.created_at
        if after and created < after:
            continue
        if before and created > before:
            continue
        items.append(item)
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": items}


@router.get("/search")
def search(
    tags: Optional[str] = Query(default=None),
    subject: Optional[str] = None,
    since: Optional[datetime] = None,
    error_type: Optional[str] = None,
    regex: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[Problem]]:
    api = _api()
    query = SearchQuery(
        tags=[tag.strip() for tag in tags.split(",") if tag.strip()]
        if tags
        else [],
        subject=subject,
        since=since,
        error_type=error_type,
        regex=regex,
        limit=limit,
    )
    return {"results": Searcher(api.TASK_STORE.list_all()).search(query)}


@router.get("/tags")
def list_tags(
    dimension: Optional[TagDimension] = None,
    query: Optional[str] = None,
    subject: Optional[str] = None,
    scope: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    items = (
        _source_tag_items(query, subject, limit)
        if dimension == TagDimension.META
        else api.TAG_STORE.search(
            dimension,
            query,
            limit,
            subject=subject,
            scope=scope,
        )
    )
    reference_counts = _tag_reference_counts()
    return {
        "items": [
            {
                **item.model_dump(mode="json"),
                "ref_count": reference_counts.get((item.dimension, item.value), 0),
            }
            for item in items
        ]
    }


@router.get("/tags/tree")
def get_knowledge_tree(subject: Optional[str] = None) -> dict[str, Any]:
    return _api().TAG_STORE.knowledge_tree(subject)


@router.post("/tags")
def create_tag(payload: TagInput) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    api.TAG_STORE.upsert(
        payload.dimension,
        payload.value,
        payload.aliases,
        payload.subject,
    )
    return list_tags(
        dimension=payload.dimension,
        query=payload.value,
        subject=payload.subject,
        limit=100,
    )


@router.get("/tags/dimensions")
@router.get("/settings/tag-dimensions")
def get_tag_dimensions() -> dict[str, Any]:
    return {"dimensions": _api().TAG_DIMENSIONS}


@router.put("/settings/tag-dimensions")
def update_tag_dimensions(payload: dict[str, Any]) -> dict[str, Any]:
    api = _api()
    dimensions = payload.get("dimensions")
    if isinstance(dimensions, dict):
        for key, value in dimensions.items():
            if key in api.TAG_DIMENSIONS and isinstance(value, dict):
                api.TAG_DIMENSIONS[key] = value
        api.APP_SETTINGS_STORE.update({"tag_dimensions": api.TAG_DIMENSIONS})
    return {"dimensions": api.TAG_DIMENSIONS}


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: str) -> dict[str, Any]:
    api = _api()
    existing = api.TAG_STORE.get_by_id(tag_id)
    if not existing or existing.source != "user":
        raise HTTPException(status_code=404, detail="User tag not found")
    references = _tag_reference_count(existing.dimension, existing.value)
    if references:
        raise HTTPException(
            status_code=409,
            detail=f"Tag is still referenced {references} times; rename or merge it first",
        )
    api.TAG_STORE.delete(tag_id)
    return {"ok": True, "tag_id": tag_id}


@router.put("/tags/{tag_id}")
def rename_tag(
    tag_id: str,
    payload: TagRenameInput,
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    existing = api.TAG_STORE.get_by_id(tag_id)
    if not existing or existing.source != "user":
        raise HTTPException(status_code=404, detail="User tag not found")
    value = payload.value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Tag value is required")
    if value != existing.value:
        api.TAG_STORE.upsert(
            existing.dimension,
            value,
            existing.aliases,
            existing.subject,
        )
        _replace_tag_references(existing.dimension, existing.value, value)
        api.TAG_STORE.delete(tag_id)
    return list_tags(dimension=existing.dimension, query=value, limit=100)


@router.post("/tags/{source_id}/merge")
def merge_tags(source_id: str, payload: dict[str, str]) -> dict[str, Any]:
    api = _api()
    source = api.TAG_STORE.get_by_id(source_id)
    target = api.TAG_STORE.get_by_id(payload.get("target_id", ""))
    if (
        not source
        or source.source != "user"
        or not target
        or source.dimension != target.dimension
    ):
        raise HTTPException(
            status_code=404,
            detail="Compatible source and target tags are required",
        )
    api.TAG_STORE.upsert(
        target.dimension,
        target.value,
        [*target.aliases, source.value, *source.aliases],
        target.subject,
    )
    tasks_modified, fields_modified = _replace_tag_references(
        source.dimension,
        source.value,
        target.value,
    )
    api.TAG_STORE.delete(source_id)
    return {
        "ok": True,
        "tasks_modified": tasks_modified,
        "fields_modified": fields_modified,
    }


@router.post("/sync")
def sync(subject: Optional[str] = None) -> dict[str, str]:
    api = _api()
    syncer = ObsidianSyncer(task_store=api.TASK_STORE, tag_store=api.TAG_STORE)
    report = syncer.sync_for_subject(subject) if subject else syncer.sync()
    return {"message": str(report)}


__all__ = ["router"]
