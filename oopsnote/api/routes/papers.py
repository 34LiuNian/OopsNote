"""Persistent paper-draft composition routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from oopsnote.core import PaperDraft, PaperDraftCreateRequest, PaperDraftUpdateRequest
from oopsnote.paper import candidate_tasks, select_paper_items

router = APIRouter()


def _api():
    from oopsnote.api import main

    return main


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


@router.get("/papers")
def list_papers() -> dict[str, list[dict[str, Any]]]:
    return {"items": [_paper_view(draft) for draft in _api().PAPER_DRAFT_STORE.list_all()]}


@router.get("/papers/candidates")
def list_paper_candidates(
    subject: str,
    knowledge_tag: Optional[list[str]] = Query(default=None),
    knowledge_node_id: Optional[list[str]] = Query(default=None),
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


@router.get("/papers/{draft_id}")
def get_paper(draft_id: str) -> dict[str, Any]:
    try:
        draft = _api().PAPER_DRAFT_STORE.get(draft_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Paper draft not found")
    return {"paper": _paper_view(draft)}


@router.patch("/papers/{draft_id}")
def update_paper(draft_id: str, payload: PaperDraftUpdateRequest) -> dict[str, Any]:
    try:
        draft = _api().PAPER_DRAFT_STORE.update(draft_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Paper draft not found")
    return {"paper": _paper_view(draft)}


@router.delete("/papers/{draft_id}")
def delete_paper(draft_id: str) -> dict[str, Any]:
    try:
        draft = _api().PAPER_DRAFT_STORE.delete(draft_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Paper draft not found")
    return {"ok": True, "paper_id": draft.id}
