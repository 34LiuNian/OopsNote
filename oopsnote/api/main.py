"""OopsNote REST API — 前端入口。

Phase 4 补全完整路由，当前提供搜索和同步端点。
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from oopsnote.core import (
    Problem,
    Searcher,
    SearchQuery,
    TaskStore,
    TagStore,
)
from oopsnote.obsidian.syncer import ObsidianSyncer

# ── 存储实例 ──────────────────────────────────────────

from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage"
TASK_STORE = TaskStore(base_dir=STORAGE_DIR)
TAG_STORE = TagStore(
    user_path=STORAGE_DIR / "settings" / "tags_user.json",
    builtin_path=STORAGE_DIR / "settings" / "tags_builtin.json",
)

# ── App ────────────────────────────────────────────────

app = FastAPI(title="OopsNote", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 模型 ──────────────────────────────────────────────


class TaskOut(BaseModel):
    id: str
    subject: str
    status: str
    problems_count: int
    created_at: str


class SearchOut(BaseModel):
    results: list[Problem]


class SyncOut(BaseModel):
    message: str


# ── 路由 ──────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


@app.get("/tasks")
def list_tasks(limit: int = 20) -> list[TaskOut]:
    tasks = TASK_STORE.list_all()
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return [
        TaskOut(
            id=t.id,
            subject=t.subject,
            status=t.status.value,
            problems_count=len(t.problems),
            created_at=t.created_at.isoformat(),
        )
        for t in tasks[:limit]
    ]


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    try:
        task = TASK_STORE.get(task_id)
        return task.model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks")
def create_task(
    subject: str = "",
) -> dict:
    """创建新任务（轻量版，完整版由 MCP 提供）。"""
    from oopsnote.core import TaskCreateRequest
    task = TASK_STORE.create(TaskCreateRequest(subject=subject))
    return {"task_id": task.id, "status": task.status.value}


@app.get("/search")
def search(
    tags: Optional[str] = Query(None, description="逗号分隔的标签"),
    subject: Optional[str] = None,
    since: Optional[str] = None,
    error_type: Optional[str] = None,
    regex: Optional[str] = None,
    limit: int = 50,
) -> list[Problem]:
    """多维度搜索题目。"""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    query = SearchQuery(
        tags=tag_list,
        subject=subject,
        since=since,
        error_type=error_type,
        regex=regex,
        limit=limit,
    )
    searcher = Searcher(TASK_STORE.list_all())
    return searcher.search(query)


@app.get("/tags")
def list_tags(
    dimension: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50,
) -> list:
    """列出标签。"""
    from oopsnote.core import TagDimension
    dim = TagDimension(dimension) if dimension else None
    return TAG_STORE.search(dimension=dim, query=query, limit=limit)


@app.post("/sync")
def sync(subject: Optional[str] = None) -> SyncOut:
    """触发 Obsidian 同步。"""
    syncer = ObsidianSyncer(
        task_store=TASK_STORE,
        tag_store=TAG_STORE,
    )
    if subject:
        report = syncer.sync_for_subject(subject)
    else:
        report = syncer.sync()
    return SyncOut(message=str(report))
