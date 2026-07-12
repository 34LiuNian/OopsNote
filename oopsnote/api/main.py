"""OopsNote REST API — 前端入口。

轻量 FastAPI 应用，只有 /health 和 /tasks 基础路由。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="OopsNote", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tasks")
def create_task() -> dict:
    """桩：创建任务。Phase 4 补全。"""
    return {"task_id": "placeholder", "status": "not_implemented"}


@app.get("/tasks")
def list_tasks() -> dict:
    """桩：列出任务。"""
    return {"tasks": [], "status": "not_implemented"}


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    """桩：获取任务详情。"""
    return {"task_id": task_id, "status": "not_implemented"}
