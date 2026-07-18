"""OopsNote MCP Server — Hermes ↔ Core 唯一通道。

FastMCP stdio server，暴露 CRUD 工具供 Hermes skill 调用。
纯数据操作，不涉及 AI。AI 流水线由 Hermes orchestrator skill 编排。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from oopsnote.core import (
    AssetStore,
    Problem,
    Searcher,
    SearchQuery,
    TagCreateRequest,
    TagDimension,
    TagItem,
    TagStore,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    TaskStore,
)

# ── Server ───────────────────────────────────────────

mcp = FastMCP("OopsNote", log_level="WARNING")

# ── 存储实例（共享） ──────────────────────────────────

STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage"
TASK_STORE = TaskStore(base_dir=STORAGE_DIR)
TAG_STORE = TagStore(
    user_path=STORAGE_DIR / "settings" / "tags_user.json",
    builtin_path=STORAGE_DIR / "settings" / "tags_builtin.json",
)
ASSET_STORE = AssetStore(base_dir=STORAGE_DIR / "assets")


# ═════════════════════════════════════════════════════
# 任务
# ═════════════════════════════════════════════════════


@mcp.tool()
def create_task(
    subject: str = "",
    asset_path: Optional[str] = None,
    asset_base64: Optional[str] = None,
) -> TaskRecord:
    """创建新任务。可附带图片路径或 base64（资产自动落盘）。"""
    payload = TaskCreateRequest(
        subject=subject,
        asset_path=asset_path,
        asset_base64=asset_base64,
    )

    task = TASK_STORE.create(payload)

    # 如果传了 base64 图片，落盘后更新 asset_path
    if asset_base64:
        path = ASSET_STORE.save_base64(asset_base64)
        task = TASK_STORE.update(task.id, asset_path=path)

    return task


@mcp.tool()
def get_task(task_id: str) -> Optional[TaskRecord]:
    """按 ID 获取任务。"""
    try:
        return TASK_STORE.get(task_id)
    except KeyError:
        return None


@mcp.tool()
def list_tasks(
    status: Optional[str] = None,
    limit: int = 20,
) -> list[TaskRecord]:
    """列出任务。可按状态过滤。"""
    tasks = TASK_STORE.list_all()
    if status:
        tasks = [t for t in tasks if t.status.value == status]
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return tasks[:limit]


@mcp.tool()
def update_task(
    task_id: str,
    status: Optional[str] = None,
    subject: Optional[str] = None,
    last_error: Optional[str] = None,
) -> Optional[TaskRecord]:
    """更新任务字段。"""
    fields: dict = {}
    if status is not None:
        fields["status"] = TaskStatus(status)
    if subject is not None:
        fields["subject"] = subject
    if last_error is not None:
        fields["last_error"] = last_error
    try:
        return TASK_STORE.update(task_id, **fields)
    except KeyError:
        return None


@mcp.tool()
def mark_task_status(
    task_id: str,
    status: str,
    error: Optional[str] = None,
) -> Optional[TaskRecord]:
    """标记任务状态。status: pending/processing/completed/failed/cancelled"""
    try:
        return TASK_STORE.mark_status(task_id, TaskStatus(status), error)
    except (KeyError, ValueError):
        return None


@mcp.tool()
def set_task_problems(
    task_id: str,
    problems_json: str,
) -> Optional[TaskRecord]:
    """批量设标题目列表。problems_json 是 Problem 列表的 JSON 字符串。"""
    import json

    raw = json.loads(problems_json)
    problems = [Problem(**p) for p in raw]
    try:
        return TASK_STORE.set_problems(task_id, problems)
    except KeyError:
        return None


# ═════════════════════════════════════════════════════
# 标签
# ═════════════════════════════════════════════════════


@mcp.tool()
def list_tags(
    dimension: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 50,
) -> list[TagItem]:
    """列出标签。可用 dimension (knowledge/error/meta/custom) 和 query 过滤。"""
    dim = None
    if dimension:
        dim = TagDimension(dimension)
    return TAG_STORE.search(dimension=dim, query=query, limit=limit)


@mcp.tool()
def create_tag(
    dimension: str,
    value: str,
    aliases: Optional[list[str]] = None,
    subject: Optional[str] = None,
) -> TagItem:
    """创建或更新标签。已存在则合并 aliases。"""
    return TAG_STORE.upsert(
        dimension=TagDimension(dimension),
        value=value,
        aliases=aliases or [],
        subject=subject,
    )


@mcp.tool()
def delete_tag(tag_id: str) -> bool:
    """按 ID 删除用户标签。内置标签不可删。"""
    return TAG_STORE.delete(tag_id)


# ═════════════════════════════════════════════════════
# 搜索
# ═════════════════════════════════════════════════════


@mcp.tool()
def search_problems(
    tags: Optional[list[str]] = None,
    subject: Optional[str] = None,
    since: Optional[str] = None,
    error_type: Optional[str] = None,
    regex: Optional[str] = None,
    limit: int = 50,
) -> list[Problem]:
    """多维度搜索题目。支持标签、学科、时间、错因、正则全文搜索。"""
    query = SearchQuery(
        tags=tags or [],
        subject=subject,
        since=since,
        error_type=error_type,
        regex=regex,
        limit=limit,
    )
    searcher = Searcher(TASK_STORE.list_all())
    return searcher.search(query)


# ═════════════════════════════════════════════════════
# 资产
# ═════════════════════════════════════════════════════


@mcp.tool()
def get_asset_path(asset_path: str) -> Optional[str]:
    """获取资产文件的绝对路径（供 Hermes vision_analyze 加载图片）。"""
    full = STORAGE_DIR / asset_path.lstrip("/")
    if full.exists():
        return str(full.resolve())
    return None


# ═════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════


def main() -> None:
    """运行 MCP server（stdio 模式）。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
