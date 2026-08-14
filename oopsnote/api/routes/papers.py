"""Persistent paper-draft composition routes."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response

from oopsnote.api.errors import ApiErrorCategory, api_error
from oopsnote.api.schemas import PaperCompileRequest, PaperDraftCompileRequest
from oopsnote.core import (
    PaperDraft,
    PaperDraftCreateRequest,
    PaperDraftItem,
    PaperDraftUpdateRequest,
)
from oopsnote.paper import (
    PaperCompileError,
    PaperCompileFailure,
    PaperDocument,
    PaperDocumentError,
    build_paper_document,
    candidate_tasks,
    compile_paper_pdf,
    select_paper_items,
)

router = APIRouter()


def _api():
    from oopsnote.api import main

    return main.request_api()


def _task_lookup() -> dict[str, Any]:
    return {task.id: task for task in _api().TASK_STORE.list_all()}


def _expanded_knowledge_tags(subject: str, node_ids: list[str], labels: list[str]) -> list[str]:
    selected_ids = set(node_ids)
    expanded = list(labels)
    document = _api().TAG_STORE.knowledge_tree(subject)

    def visit(node: dict[str, Any], ancestor_selected: bool = False) -> None:
        if node.get("scope") and node.get("scope") != "core":
            return
        directly_selected = node.get("id") in selected_ids
        selected = ancestor_selected or directly_selected
        if selected and (directly_selected or node.get("selectable")) and node.get("title"):
            expanded.append(str(node["title"]))
        for child in node.get("children", []):
            visit(child, selected)

    subject_tree = document.get("subjects", {}).get(subject)
    if subject_tree and subject_tree.get("root"):
        visit(subject_tree["root"])
    return list(dict.fromkeys(expanded))


def _paper_view(draft: PaperDraft) -> dict[str, Any]:
    api = _api()
    tasks = _task_lookup()
    items = []
    for item in draft.items:
        task = tasks.get(item.task_id)
        problem_view = None
        if task and task.problem and task.problem.id == item.problem_id:
            problem_view = api._problem_summary(task, task.problem)
            problem_view["difficulty_coefficient"] = item.difficulty_coefficient
        items.append({**item.model_dump(mode="json"), "problem": problem_view})
    return {**draft.model_dump(mode="json"), "items": items}


def _compile_error_response(error: PaperCompileError) -> HTTPException:
    if error.code == PaperCompileFailure.MISSING_ENGINE:
        status = 503
    elif error.code == PaperCompileFailure.ENGINE_TIMEOUT:
        status = 504
    else:
        status = 422
    request_failure = error.code in {
        PaperCompileFailure.INVALID_CONTENT,
        PaperCompileFailure.MISSING_ASSET,
        PaperCompileFailure.UNSUPPORTED_ASSET,
    }
    return api_error(
        status,
        code=error.code.value.replace("-", "_"),
        message=str(error),
        category=(ApiErrorCategory.REQUEST if request_failure else ApiErrorCategory.INTERNAL),
        retryable=error.code == PaperCompileFailure.ENGINE_TIMEOUT,
        scope="paper_compile",
        details={"log": error.log} if error.log else None,
    )


def _document_error_response(error: PaperDocumentError) -> HTTPException:
    status = 409 if error.code in {"missing-task", "missing-problem"} else 422
    return api_error(
        status,
        code=error.code.replace("-", "_"),
        message=str(error),
        category=ApiErrorCategory.REQUEST,
        scope="paper_compile",
        details={"item_id": error.item_id} if error.item_id else None,
    )


def _pdf_response(content: bytes, title: str) -> Response:
    safe_name = "".join(char for char in title if char not in '\\/:*?"<>|').strip() or "paper"
    encoded_name = quote(f"{safe_name}.pdf")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=oopsnote-paper.pdf; filename*=UTF-8''{encoded_name}"
            )
        },
    )


def _compile_document(document: PaperDocument) -> Response:
    try:
        content = compile_paper_pdf(
            document,
            asset_path_resolver=_api().ASSET_STORE.resolve,
        )
    except PaperCompileError as error:
        raise _compile_error_response(error) from error
    return _pdf_response(content, document.title)


@router.get("/papers")
def list_papers() -> dict[str, list[dict[str, Any]]]:
    return {"items": [_paper_view(draft) for draft in _api().PAPER_DRAFT_STORE.list_all()]}


@router.get("/papers/candidates")
def list_paper_candidates(
    subject: str,
    knowledge_tag: list[str] | None = Query(default=None),
    knowledge_node_id: list[str] | None = Query(default=None),
    limit: int = Query(default=250, ge=1, le=1000),
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    items = []
    for task, coefficient in candidate_tasks(
        api.TASK_STORE.list_all(),
        subject=subject,
        knowledge_tags=_expanded_knowledge_tags(
            subject,
            knowledge_node_id or [],
            knowledge_tag or [],
        ),
    )[:limit]:
        problem = api._problem_summary(task, task.problem)
        problem["difficulty_coefficient"] = coefficient
        items.append(problem)
    return {"items": items}


@router.post("/papers", status_code=201)
def create_paper(payload: PaperDraftCreateRequest) -> dict[str, Any]:
    selection_payload = payload.model_copy(
        update={
            "knowledge_tags": _expanded_knowledge_tags(
                payload.subject,
                payload.knowledge_node_ids,
                payload.knowledge_tags,
            )
        }
    )
    items = (
        select_paper_items(_api().TASK_STORE.list_all(), selection_payload)
        if payload.auto_select
        else []
    )
    draft = _api().PAPER_DRAFT_STORE.create(payload, items=items)
    return {"paper": _paper_view(draft)}


@router.post("/papers/compile")
def compile_paper(payload: PaperCompileRequest) -> Response:
    tasks = _task_lookup()
    draft_items = []
    for item in payload.items:
        task = tasks.get(item.task_id)
        if not task or not task.problem or task.problem.id != item.problem_id:
            raise HTTPException(
                status_code=404,
                detail=f"Problem {item.problem_id} was not found on task {item.task_id}",
            )
        draft_items.append(
            PaperDraftItem(
                task_id=item.task_id,
                problem_id=item.problem_id,
                question_type=task.problem.question_type.value,
            )
        )
    draft_subject = tasks[draft_items[0].task_id].subject if draft_items else ""
    try:
        document = build_paper_document(
            PaperDraft(title=payload.title, subject=draft_subject, items=draft_items),
            tasks,
            subtitle=payload.subtitle or "",
            show_answers=payload.show_answers,
        )
    except PaperDocumentError as error:
        raise _document_error_response(error) from error
    return _compile_document(document)


@router.post("/papers/{draft_id}/compile")
def compile_paper_draft(draft_id: str, payload: PaperDraftCompileRequest) -> Response:
    try:
        draft = _api().PAPER_DRAFT_STORE.get(draft_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found") from error
    try:
        document = build_paper_document(
            draft,
            _task_lookup(),
            subtitle=payload.subtitle or "",
            show_answers=payload.show_answers,
        )
    except PaperDocumentError as error:
        raise _document_error_response(error) from error
    return _compile_document(document)


@router.get("/papers/{draft_id}")
def get_paper(draft_id: str) -> dict[str, Any]:
    try:
        draft = _api().PAPER_DRAFT_STORE.get(draft_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found") from error
    return {"paper": _paper_view(draft)}


@router.patch("/papers/{draft_id}")
def update_paper(draft_id: str, payload: PaperDraftUpdateRequest) -> dict[str, Any]:
    try:
        draft = _api().PAPER_DRAFT_STORE.update(draft_id, payload)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found") from error
    return {"paper": _paper_view(draft)}


@router.delete("/papers/{draft_id}")
def delete_paper(draft_id: str) -> dict[str, Any]:
    try:
        draft = _api().PAPER_DRAFT_STORE.delete(draft_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Paper draft not found") from error
    return {"ok": True, "paper_id": draft.id}
