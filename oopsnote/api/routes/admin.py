"""Administrator-only application membership and quota projections."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from oopsnote.api.auth import AuthenticationError, require_admin_request
from oopsnote.core import Principal

router = APIRouter(prefix="/admin/members", tags=["admin-members"])
internal_router = APIRouter(prefix="/internal", tags=["internal-members"])


class ProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_user_id: str = Field(min_length=1, max_length=256)
    daily_success_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    max_concurrent_runs: int | None = Field(default=None, ge=1, le=64)


class QuotaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_success_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    max_concurrent_runs: int | None = Field(default=None, ge=1, le=64)


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_user_ids: list[str] = Field(min_length=1, max_length=100)


class SelfProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_success_limit: int = Field(ge=0, le=1_000_000)


def _api():
    from oopsnote.api import main

    return main


def _require_admin(request: Request) -> None:
    try:
        require_admin_request(request)
    except AuthenticationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.post("/provision")
def provision_member(payload: ProvisionRequest, request: Request) -> dict[str, Any]:
    _require_admin(request)
    api = _api()
    try:
        workspace = api.WORKSPACE_REGISTRY.provision(
            payload.auth_user_id,
            daily_success_limit=payload.daily_success_limit,
            max_concurrent_runs=payload.max_concurrent_runs,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "auth_user_id": payload.auth_user_id,
        "workspace_id": str(workspace.workspace_id),
        "quota": api.WORKSPACE_REGISTRY.quota_summary(payload.auth_user_id),
    }


@router.post("/summary")
def member_summaries(payload: SummaryRequest, request: Request) -> dict[str, Any]:
    _require_admin(request)
    return {"members": _api().WORKSPACE_REGISTRY.quota_summaries(payload.auth_user_ids)}


@router.patch("/{auth_user_id}/quota")
def update_member_quota(auth_user_id: str, payload: QuotaPatch, request: Request) -> dict[str, Any]:
    _require_admin(request)
    if payload.daily_success_limit is None and payload.max_concurrent_runs is None:
        raise HTTPException(status_code=400, detail="至少提供一个额度字段")
    try:
        quota = _api().WORKSPACE_REGISTRY.update_quota(
            auth_user_id,
            daily_success_limit=payload.daily_success_limit,
            max_concurrent_runs=payload.max_concurrent_runs,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="用户尚未拥有工作区") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"auth_user_id": auth_user_id, "quota": quota}


@internal_router.post("/members/provision-self")
def provision_self(payload: SelfProvisionRequest, request: Request) -> dict[str, Any]:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401, detail="Missing authenticated user")
    api = _api()
    workspace = api.WORKSPACE_REGISTRY.provision(
        principal.user_id,
        daily_success_limit=payload.daily_success_limit,
    )
    return {
        "auth_user_id": principal.user_id,
        "workspace_id": str(workspace.workspace_id),
        "quota": api.WORKSPACE_REGISTRY.quota_summary(principal.user_id),
    }
