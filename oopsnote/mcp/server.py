"""OopsNote MCP Server — the restricted AI ↔ Core boundary.

FastMCP stdio server，暴露 CRUD 工具供 the managed Pi pipeline 调用。
纯数据操作，不涉及 AI；AI 流水线由 managed runner 编排。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP

from oopsnote.catalog import KNOWLEDGE_TAGS_PATH, KNOWLEDGE_TREES_PATH
from oopsnote.content import validate_answer_conclusion
from oopsnote.core import (
    AssetStore,
    ContentFormat,
    Problem,
    RunArtifact,
    RunStatus,
    RunStore,
    RunValidationError,
    Searcher,
    SearchQuery,
    StateConflict,
    TagCreateRequest,
    TagDimension,
    TagItem,
    TagStore,
    TaskCreateRequest,
    TaskRecord,
    SolutionCandidate,
    TaskStage,
    TaskStatus,
    TaskStore,
    subjects_match,
)
from oopsnote.obsidian.syncer import OBSIDIAN_SYNC_QUEUE, ObsidianSyncer

# ── Server ───────────────────────────────────────────

mcp = FastMCP("OopsNote", log_level="WARNING")
INTAKE_REVIEW_REASONS = {
    "unreadable",
    "incomplete",
    "multiple_questions",
    "other",
}
PIPELINE_STAGE_PREDECESSORS = {
    TaskStage.OCR: {None, TaskStage.STARTING},
    TaskStage.SOLVING: {TaskStage.OCR},
    TaskStage.VERIFYING: {TaskStage.SOLVING},
    TaskStage.TAGGING: {TaskStage.VERIFYING},
    TaskStage.FINALIZING: {TaskStage.TAGGING},
}
ManagedStage = Literal["ocr", "solving", "verifying", "tagging", "finalizing"]
ManagedReviewReason = Literal[
    "",
    "unreadable",
    "incomplete",
    "multiple_questions",
    "other",
]
ManagedStudentResponseStatus = Literal["answered", "unanswered", "unknown"]


def _require_active_run(task_id: str, run_id: str) -> TaskRecord:
    task = TASK_STORE.get(task_id)
    if not run_id or task.active_run_id != run_id:
        raise ValueError(f"run_id {run_id} is not active for task {task_id}")
    return task


def _task_metadata_with_review(task: TaskRecord, review_reason: str) -> dict:
    metadata = dict(task.metadata)
    metadata.pop("_managed_knowledge_branches", None)
    metadata.pop("_managed_tag_selection", None)
    metadata.pop("_managed_error_candidates", None)
    metadata.pop("intake_review_reason", None)
    if review_reason:
        if review_reason not in INTAKE_REVIEW_REASONS:
            raise ValueError(f"invalid review_reason: {review_reason}")
        metadata["intake_review_reason"] = review_reason
    return metadata


def _managed_task_context(task: TaskRecord) -> dict[str, Any]:
    """Return only task fields the managed agent can act on."""

    metadata = task.metadata
    return {
        "task_id": task.id,
        "status": task.status.value,
        "subject": task.subject,
        "asset_path": task.asset_path,
        "question_no": metadata.get("question_no"),
        "source": metadata.get("source"),
        "notes": metadata.get("notes") or "",
        "hints": {
            key: metadata.get(key)
            for key in (
                "question_type",
                "difficulty",
                "knowledge_tags",
                "error_tags",
                "user_tags",
            )
            if metadata.get(key)
        },
    }


def _task_ack(task: TaskRecord, **fields: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "task_id": task.id,
        "status": task.status.value,
        **fields,
    }


def _update_completed_task_message(
    task_id: str,
    problem_id: str,
    message: str,
) -> Optional[TaskRecord]:
    """Attach derived-work status only while the same completion is current."""
    try:
        return TASK_STORE.transition(
            task_id,
            expected_statuses={TaskStatus.COMPLETED},
            expected_active_run_id=None,
            expected_problem_id=problem_id,
            stage_message=message,
        )
    except (KeyError, StateConflict):
        return None

# ── 存储实例（共享） ──────────────────────────────────

STORAGE_DIR = Path(os.getenv("OOPSNOTE_STORAGE_DIR", str(Path(__file__).resolve().parents[2] / "storage")))
TASK_STORE = TaskStore(base_dir=STORAGE_DIR)
TAG_STORE = TagStore(
    user_path=STORAGE_DIR / "settings" / "tags_user.json",
    builtin_path=KNOWLEDGE_TAGS_PATH,
    tree_path=KNOWLEDGE_TREES_PATH,
)
ASSET_STORE = AssetStore(base_dir=STORAGE_DIR / "assets")
RUN_STORE = RunStore(base_dir=STORAGE_DIR / "runs")


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
def get_task(task_id: str, run_id: str) -> dict[str, Any]:
    """Get only the task bound to the currently active managed run."""
    return _managed_task_context(_require_active_run(task_id, run_id))


def _active_task_run(task_id: str, run_id: str):
    """Return the lifecycle-owned run after checking it matches the active task."""

    try:
        run = RUN_STORE.get(run_id)
    except KeyError as error:
        raise ValueError(f"run_id {run_id} has no managed run record") from error
    if run.task_id != task_id:
        raise ValueError(f"run_id {run_id} does not belong to task {task_id}")
    if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
        raise ValueError(f"run_id {run_id} is not active")
    return run


def _parse_pipeline_problem(task: TaskRecord, problem_json: str) -> tuple[Problem, str]:
    """Validate the content shape shared by solver candidates and final output."""

    import json

    raw = json.loads(problem_json)
    if not isinstance(raw, dict):
        raise ValueError("problem_json must be a JSON object")
    problem = Problem.model_validate(raw)
    if problem.content_format != ContentFormat.OOPSMARK_V1:
        raise ValueError("problem must declare content_format=oopsmark-v1")
    answer_issue = validate_answer_conclusion(problem.answer)
    if answer_issue:
        raise ValueError(
            f"answer:{answer_issue.line} [{answer_issue.code}] {answer_issue.message}"
        )
    missing = [
        name for name in ("subject", "problem_text", "answer", "explanation")
        if not getattr(problem, name).strip()
    ]
    if missing:
        raise ValueError(f"problem missing required fields: {', '.join(missing)}")
    if problem.question_type.value in {"单选题", "多选题"} and len(problem.options) < 2:
        raise ValueError("problem selection options are incomplete")

    subject = task.subject
    if not subject or subject == "auto":
        subject = problem.subject
    elif not subjects_match(problem.subject, subject):
        raise ValueError(
            f"problem subject {problem.subject} does not match task subject {subject}"
        )
    return problem, subject


def _record_validation_error(
    run_id: str,
    stage: TaskStage,
    raw_output: str,
    error: ValueError,
) -> None:
    """Retain rejected managed output on its run without changing task state."""
    RUN_STORE.record_validation_error(
        run_id,
        RunValidationError(
            stage=stage,
            raw_output=raw_output,
            message=str(error),
        ),
    )


def _raise_validation_error(
    run_id: str,
    stage: TaskStage,
    raw_output: str,
    message: str,
) -> None:
    error = ValueError(message)
    _record_validation_error(run_id, stage, raw_output, error)
    raise error


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
def report_task_stage(
    task_id: str,
    stage: ManagedStage,
    run_id: str,
    message: Optional[str] = None,
) -> dict[str, Any]:
    """上报受管 AI 任务阶段。stage: ocr/solving/verifying/tagging/finalizing。"""
    current = _require_active_run(task_id, run_id)
    requested_stage = TaskStage(stage)
    if requested_stage == TaskStage.VERIFYING:
        run = _active_task_run(task_id, run_id)
        if run.solution_candidate is None or run.verification_started_at is None:
            raise ValueError(
                "verifying requires a solver candidate and a runner-started independent session"
            )
    if current.stage == requested_stage:
        return _task_ack(current, stage=requested_stage.value)
    expected = PIPELINE_STAGE_PREDECESSORS.get(requested_stage)
    if expected is not None and current.stage not in expected:
        previous = current.stage.value if current.stage else "none"
        raise ValueError(
            f"stage {requested_stage.value} cannot follow {previous}"
        )
    task = TASK_STORE.transition(
        task_id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=run_id,
        stage=requested_stage,
        stage_message=message,
    )
    return _task_ack(task, stage=task.stage.value if task.stage else None)


@mcp.tool()
def submit_solution_candidate(
    task_id: str,
    problem_json: str,
    run_id: str,
    review_reason: ManagedReviewReason = "",
    student_response_status: ManagedStudentResponseStatus = "unknown",
) -> dict[str, Any]:
    """Store one solver candidate for a fresh verification session; this never finalizes a task."""

    task = _require_active_run(task_id, run_id)
    if task.stage != TaskStage.SOLVING:
        current_stage = task.stage.value if task.stage else "none"
        raise ValueError(
            "submit_solution_candidate requires the pipeline to be solving; "
            f"current stage is {current_stage}"
        )
    run = _active_task_run(task_id, run_id)
    try:
        problem, _subject = _parse_pipeline_problem(task, problem_json)
    except ValueError as error:
        _record_validation_error(run.id, TaskStage.SOLVING, problem_json, error)
        raise
    try:
        candidate = SolutionCandidate(
            problem=problem,
            review_reason=review_reason,
            student_response_status=student_response_status,
        )
    except ValueError as error:
        _record_validation_error(run.id, TaskStage.SOLVING, problem_json, error)
        raise
    try:
        RUN_STORE.submit_solution_candidate(
            run.id,
            candidate,
            RunArtifact(
                stage=TaskStage.SOLVING,
                kind="solver_candidate",
                raw_output=problem_json,
                parsed_output={
                    "problem": candidate.problem.model_dump(mode="json"),
                    "review_reason": candidate.review_reason,
                    "student_response_status": candidate.student_response_status,
                },
            ),
        )
    except StateConflict as error:
        raise ValueError(str(error)) from error
    metadata = dict(task.metadata)
    metadata.pop("_managed_tag_selection", None)
    metadata.pop("_managed_error_candidates", None)
    TASK_STORE.transition(
        task_id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=run_id,
        metadata=metadata,
    )
    return _task_ack(task, candidate_submitted=True)


@mcp.tool()
def fail_task(
    task_id: str,
    error: str,
    run_id: str,
    review_reason: ManagedReviewReason = "",
) -> dict[str, Any]:
    """以明确原因终止当前受管 AI 任务，可同时标记需人工复核。"""
    return _fail_active_task(
        task_id,
        error,
        run_id=run_id,
        error_code="pipeline_failed",
        review_reason=review_reason,
    )


def _fail_active_task(
    task_id: str,
    error: str,
    *,
    run_id: str,
    error_code: str,
    review_reason: ManagedReviewReason = "",
) -> dict[str, Any]:
    """Atomically persist one classified failure for the active managed run."""
    task = _require_active_run(task_id, run_id)
    failed = TASK_STORE.transition(
        task_id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=run_id,
        status=TaskStatus.FAILED,
        stage_message=error,
        active_run_id=None,
        last_error=error,
        last_error_code=error_code,
        metadata=_task_metadata_with_review(task, review_reason),
    )
    return _task_ack(failed, review_reason=review_reason or None)


@mcp.tool()
def finalize_task(
    task_id: str,
    problem_json: str,
    run_id: str,
    sync_to_obsidian: bool = True,
    review_reason: Optional[ManagedReviewReason] = None,
    student_response_status: Optional[ManagedStudentResponseStatus] = None,
) -> dict[str, Any]:
    """校验并原子提交 AI 结果，可同时标记需人工复核。"""
    task = _require_active_run(task_id, run_id)
    run = _active_task_run(task_id, run_id)
    candidate = run.solution_candidate
    if candidate is None or run.verification_started_at is None:
        raise ValueError(
            "finalize_task requires a solver candidate reviewed in an independent session"
        )
    if task.stage != TaskStage.FINALIZING:
        current_stage = task.stage.value if task.stage else "none"
        raise ValueError(
            "finalize_task requires the ordered pipeline to reach finalizing; "
            f"current stage is {current_stage}"
        )
    try:
        problem, subject = _parse_pipeline_problem(task, problem_json)
    except ValueError as error:
        _record_validation_error(run.id, TaskStage.FINALIZING, problem_json, error)
        raise
    if review_reason is not None and review_reason != candidate.review_reason:
        _raise_validation_error(
            run.id,
            TaskStage.FINALIZING,
            problem_json,
            "review_reason must match the solver candidate",
        )
    if (
        student_response_status is not None
        and student_response_status != candidate.student_response_status
    ):
        _raise_validation_error(
            run.id,
            TaskStage.FINALIZING,
            problem_json,
            "student_response_status must match the solver candidate",
        )
    review_reason = candidate.review_reason
    student_response_status = candidate.student_response_status

    trusted_error_hints = {
        str(value).strip()
        for value in task.metadata.get("error_tags", [])
        if str(value).strip()
    }
    if student_response_status != "answered":
        invented_errors = [
            value for value in problem.error_hypothesis
            if value not in trusted_error_hints
        ]
        if invented_errors:
            _raise_validation_error(
                run.id,
                TaskStage.FINALIZING,
                problem_json,
                "error_hypothesis requires a readable student response or an explicit "
                "user-provided error tag"
            )

    trusted_source = str(task.metadata.get("source") or "").strip()
    trusted_source_page = task.metadata.get("source_page")
    problem = problem.model_copy(
        update={
            "subject": subject,
            "source": trusted_source or problem.source,
            "source_page": (
                trusted_source_page
                if isinstance(trusted_source_page, int) and trusted_source_page > 0
                else problem.source_page
            ),
        }
    )
    if problem.knowledge_points:
        selection = task.metadata.get("_managed_tag_selection")
        if not isinstance(selection, dict) or selection.get("run_id") != run_id:
            _raise_validation_error(
                run.id,
                TaskStage.FINALIZING,
                problem_json,
                "knowledge_points require branches selected by this managed run",
            )
        if selection.get("subject") != subject:
            _raise_validation_error(
                run.id,
                TaskStage.FINALIZING,
                problem_json,
                "knowledge tag selection subject does not match the problem",
            )
        valid_leaf_values = set(TAG_STORE.ai_knowledge_leaves(
            subject,
            list(selection.get("branch_ids") or []),
            scope=selection.get("scope"),
        ))
        invalid_tags = list(dict.fromkeys(
            value for value in problem.knowledge_points
            if value not in valid_leaf_values
        ))
        if invalid_tags:
            _raise_validation_error(
                run.id,
                TaskStage.FINALIZING,
                problem_json,
                "knowledge_points must contain only knowledge-tree leaf tags; "
                f"invalid: {', '.join(invalid_tags)}"
            )
    if problem.error_hypothesis:
        valid_error_values = set(TAG_STORE.ai_values(
            dimension=TagDimension.ERROR,
            subject=subject,
            scope="core",
        ))
        invalid_errors = list(dict.fromkeys(
            value for value in problem.error_hypothesis
            if value not in valid_error_values
        ))
        if invalid_errors:
            _raise_validation_error(
                run.id,
                TaskStage.FINALIZING,
                problem_json,
                "error_hypothesis must contain existing error tags; create missing tags first; "
                f"invalid: {', '.join(invalid_errors)}"
            )
    RUN_STORE.record_artifact(
        run.id,
        RunArtifact(
            stage=TaskStage.FINALIZING,
            kind="verifier_submission",
            raw_output=problem_json,
            parsed_output=problem.model_dump(mode="json"),
        ),
    )
    completed = TASK_STORE.transition(
        task_id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=run_id,
        subject=subject,
        problem=problem,
        status=TaskStatus.COMPLETED,
        stage=TaskStage.FINALIZING,
        stage_message="AI 结果已校验并写入",
        active_run_id=None,
        last_error=None,
        last_error_code=None,
        revision_count=0,
        last_revised_at=None,
        metadata={
            **_task_metadata_with_review(task, review_reason),
            "student_response_status": student_response_status,
        },
    )
    sync_queued = False
    if sync_to_obsidian:
        try:
            syncer = ObsidianSyncer(
                task_store=TASK_STORE,
                tag_store=TAG_STORE,
                vault_root=STORAGE_DIR.parent / "vaults",
            )
            OBSIDIAN_SYNC_QUEUE.enqueue(syncer, problem, task_id=task_id)
            sync_queued = True
            sync_update = _update_completed_task_message(
                task_id,
                problem.id,
                "AI 结果已写入；Obsidian 增量同步已排队",
            )
            if sync_update is not None:
                completed = sync_update
        except Exception as error:
            sync_update = _update_completed_task_message(
                task_id,
                problem.id,
                f"AI 结果已写入；Obsidian 同步失败：{error}",
            )
            if sync_update is not None:
                completed = sync_update
    return _task_ack(
        completed,
        problem_id=problem.id,
        review_reason=review_reason or None,
        sync_queued=sync_queued,
    )


@mcp.tool()
def set_task_problem(
    task_id: str,
    problem_json: str,
) -> Optional[TaskRecord]:
    """设置任务的唯一题目。problem_json 是 Problem 对象的 JSON 字符串。"""
    import json

    problem = Problem.model_validate(json.loads(problem_json))
    try:
        return TASK_STORE.set_problem(task_id, problem)
    except KeyError:
        return None


# ═════════════════════════════════════════════════════
# 标签
# ═════════════════════════════════════════════════════


@mcp.tool()
def list_tags(
    dimension: str,
    subject: Optional[str] = None,
    scope: Optional[str] = "core",
    branch_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """渐进列出 AI 标签；知识维度先列分支，再按最多六个分支列叶子。"""
    dim = TagDimension(dimension)
    if dim == TagDimension.KNOWLEDGE:
        if not subject:
            raise ValueError("subject is required when listing knowledge tags")
        if branch_ids is None:
            return {
                "mode": "branches",
                "max_branches": 6,
                "items": TAG_STORE.ai_knowledge_branches(subject, scope=scope),
            }
        selected_branch_ids = list(dict.fromkeys(
            value.strip() for value in branch_ids if value.strip()
        ))
        return {
            "mode": "leaves",
            "branch_ids": selected_branch_ids,
            "items": TAG_STORE.ai_knowledge_leaves(
                subject,
                selected_branch_ids,
                scope=scope,
            ),
        }
    if branch_ids is not None:
        raise ValueError("branch_ids are only supported for knowledge tags")
    return {
        "mode": "values",
        "items": TAG_STORE.ai_values(
            dimension=dim,
            subject=subject,
            scope=scope,
        ),
    }


@mcp.tool()
def create_tag(
    dimension: str,
    value: str,
    aliases: Optional[list[str]] = None,
    subject: Optional[str] = None,
) -> TagItem:
    """创建或更新非知识标签。已存在则合并 aliases。"""
    dim = TagDimension(dimension)
    if dim == TagDimension.KNOWLEDGE:
        raise ValueError("managed AI cannot create knowledge tags")
    return TAG_STORE.upsert(
        dimension=dim,
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
# Obsidian 同步
# ═════════════════════════════════════════════════════


@mcp.tool()
def sync_to_obsidian(subject: Optional[str] = None) -> str:
    """同步 JSON 数据到 Obsidian vault。

    生成 .md 文件和标签索引。
    不传 subject 则同步全部学科，传则只同步指定学科。
    """
    syncer = ObsidianSyncer(
        task_store=TASK_STORE,
        tag_store=TAG_STORE,
        vault_root=STORAGE_DIR.parent / "vaults",
    )
    if subject:
        report = syncer.sync_for_subject(subject)
    else:
        report = syncer.sync()
    return str(report)


# ═════════════════════════════════════════════════════
# 资产
# ═════════════════════════════════════════════════════


@mcp.tool()
def get_asset_path(task_id: str, run_id: str) -> str:
    """Return only the asset bound to the currently active managed run."""
    task = _require_active_run(task_id, run_id)
    if not task.asset_path:
        raise ValueError(f"task {task_id} has no image asset")
    return str(ASSET_STORE.resolve(task.asset_path))


# ═════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════


def main() -> None:
    """运行 MCP server（stdio 模式）。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
