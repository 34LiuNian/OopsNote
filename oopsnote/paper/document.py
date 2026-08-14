"""Authoritative paper-document projection from persistent Core state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from oopsnote.core import ContentFormat, DiagramStatus, PaperDraft, Problem, TaskRecord

PaperAnswerSpace = Literal["compact", "standard", "large"]
PaperDiagramKind = Literal["tikz", "image"]
PaperDiagramPosition = Literal["left", "right"]


class PaperDocumentError(ValueError):
    """A deterministic contract failure while projecting one paper draft."""

    def __init__(self, code: str, message: str, *, item_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.item_id = item_id


@dataclass(frozen=True)
class PaperDiagram:
    kind: PaperDiagramKind
    source: str
    position: PaperDiagramPosition = "right"
    scale_percent: int = 100


@dataclass(frozen=True)
class PaperDocumentItem:
    id: str
    number: int
    question_type: str
    points: float | None
    answer_space: PaperAnswerSpace
    problem: Problem
    diagram: PaperDiagram | None = None


@dataclass(frozen=True)
class PaperDocumentSection:
    question_type: str
    items: tuple[PaperDocumentItem, ...]


@dataclass(frozen=True)
class PaperDocument:
    draft_id: str
    title: str
    subtitle: str
    subject: str
    show_answers: bool
    sections: tuple[PaperDocumentSection, ...]

    @property
    def items(self) -> tuple[PaperDocumentItem, ...]:
        return tuple(item for section in self.sections for item in section.items)


def _paper_diagram(task: TaskRecord, *, item_id: str) -> PaperDiagram | None:
    problem = task.problem
    if problem is None:
        return None
    if not problem.has_diagram and not task.diagram_items:
        return None
    if len(task.diagram_items) > 1:
        raise PaperDocumentError(
            "multiple-diagrams-not-supported",
            f"Problem {problem.id} has multiple diagrams; this paper layout supports one",
            item_id=item_id,
        )
    if not task.diagram_items:
        raise PaperDocumentError(
            "missing-diagram-item",
            f"Problem {problem.id} has no reconstructed diagram item",
            item_id=item_id,
        )
    item = task.diagram_items[0]
    if item.needs_review or item.status == DiagramStatus.NEEDS_REVIEW:
        raise PaperDocumentError(
            "diagram-needs-review",
            f"Problem {problem.id} has a diagram that still needs review",
            item_id=item_id,
        )

    if item.status not in {DiagramStatus.READY_TIKZ, DiagramStatus.READY_IMAGE}:
        raise PaperDocumentError(
            "diagram-not-ready",
            f"Problem {problem.id} diagram is {item.status.value}",
            item_id=item_id,
        )
    if item.status == DiagramStatus.READY_TIKZ:
        candidate = next(
            (
                candidate
                for candidate in item.candidates
                if candidate.id == item.selected_candidate_id
            ),
            None,
        )
        source = str(candidate.pdf_path if candidate else "").strip()
        kind: PaperDiagramKind = "tikz"
    else:
        source = str(item.fallback_image_path or "").strip()
        kind = "image"
    if not source:
        raise PaperDocumentError(
            "missing-diagram-source",
            f"Problem {problem.id} has no paper-ready diagram asset",
            item_id=item_id,
        )

    return PaperDiagram(
        kind=kind,
        source=source,
        position=item.position,
        scale_percent=item.scale_percent,
    )


def build_paper_document(
    draft: PaperDraft,
    tasks: Mapping[str, TaskRecord],
    *,
    subtitle: str = "",
    show_answers: bool = False,
) -> PaperDocument:
    """Project one persistent draft into the only semantic export document."""

    if not draft.items:
        raise PaperDocumentError("empty-paper", "Paper draft has no questions")

    sections: list[PaperDocumentSection] = []
    current_type: str | None = None
    current_items: list[PaperDocumentItem] = []

    def flush_section() -> None:
        nonlocal current_items, current_type
        if current_type is not None and current_items:
            sections.append(PaperDocumentSection(current_type, tuple(current_items)))
        current_items = []

    for number, draft_item in enumerate(draft.items, start=1):
        task = tasks.get(draft_item.task_id)
        if task is None:
            raise PaperDocumentError(
                "missing-task",
                f"Paper item {draft_item.id} references missing task {draft_item.task_id}",
                item_id=draft_item.id,
            )
        problem = task.problem
        if problem is None or problem.id != draft_item.problem_id:
            raise PaperDocumentError(
                "missing-problem",
                f"Paper item {draft_item.id} references unavailable problem {draft_item.problem_id}",
                item_id=draft_item.id,
            )
        if problem.content_format != ContentFormat.OOPSMARK_V1:
            raise PaperDocumentError(
                "unsupported-content-format",
                f"Problem {problem.id} uses {problem.content_format.value}; migrate it to oopsmark-v1 before export",
                item_id=draft_item.id,
            )
        if show_answers and not problem.answer.strip():
            raise PaperDocumentError(
                "missing-answer",
                f"Problem {problem.id} has no answer for the answer-version export",
                item_id=draft_item.id,
            )

        if current_type != draft_item.question_type:
            flush_section()
            current_type = draft_item.question_type
        current_items.append(
            PaperDocumentItem(
                id=draft_item.id,
                number=number,
                question_type=draft_item.question_type,
                points=draft_item.points,
                answer_space=draft_item.answer_space,
                problem=problem,
                diagram=_paper_diagram(task, item_id=draft_item.id),
            )
        )

    flush_section()
    return PaperDocument(
        draft_id=draft.id,
        title=draft.title.strip() or "未命名试卷",
        subtitle=subtitle.strip(),
        subject=draft.subject,
        show_answers=show_answers,
        sections=tuple(sections),
    )


__all__ = [
    "PaperDiagram",
    "PaperDocument",
    "PaperDocumentError",
    "PaperDocumentItem",
    "PaperDocumentSection",
    "build_paper_document",
]
