"""Authoritative paper-document projection from persistent Core state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from oopsnote.content import validate_oopsmark
from oopsnote.core import ContentFormat, PaperDraft, Problem, TaskRecord


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
    metadata = task.metadata
    detected = bool(metadata.get("diagram_detected", problem.has_diagram))
    if not detected:
        return None
    if metadata.get("diagram_needs_review"):
        raise PaperDocumentError(
            "diagram-needs-review",
            f"Problem {problem.id} has a diagram that still needs review",
            item_id=item_id,
        )

    kind = metadata.get("diagram_kind")
    if kind not in {"tikz", "image"}:
        raise PaperDocumentError(
            "missing-diagram-kind",
            f"Problem {problem.id} has no exportable structured diagram",
            item_id=item_id,
        )
    position = metadata.get("diagram_position", "right")
    if position not in {"left", "right"}:
        raise PaperDocumentError(
            "invalid-diagram-position",
            f"Problem {problem.id} has invalid diagram position {position!r}",
            item_id=item_id,
        )
    raw_scale = metadata.get("diagram_scale_percent")
    scale = 100 if raw_scale is None else int(raw_scale)
    if scale < 50 or scale > 200:
        raise PaperDocumentError(
            "invalid-diagram-scale",
            f"Problem {problem.id} has diagram scale outside 50..200",
            item_id=item_id,
        )

    if kind == "tikz":
        source = str(metadata.get("diagram_tikz_source") or "").strip()
        if not source:
            raise PaperDocumentError(
                "missing-diagram-source",
                f"Problem {problem.id} has no persisted TikZ source",
                item_id=item_id,
            )
        issues = [
            issue
            for issue in validate_oopsmark(f"```tikz\n{source}\n```")
            if issue.severity == "error"
        ]
        if issues:
            first = issues[0]
            raise PaperDocumentError(
                "invalid-diagram-source",
                f"Problem {problem.id} diagram is unsafe or invalid: {first.message}",
                item_id=item_id,
            )
    else:
        source = str(metadata.get("diagram_image_path") or "").strip()
        if not source:
            raise PaperDocumentError(
                "missing-diagram-source",
                f"Problem {problem.id} has no persisted diagram image",
                item_id=item_id,
            )

    return PaperDiagram(
        kind=kind,
        source=source,
        position=position,
        scale_percent=scale,
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
