"""Application boundary for rendering and persisting a selected TikZ candidate."""

from __future__ import annotations

from dataclasses import dataclass

from oopsnote.ai.diagram_renderer import TikzRenderClient
from oopsnote.core import (
    AssetStore,
    DiagramCandidate,
    DiagramStatus,
    StateConflict,
    TaskRecord,
    TaskStore,
)


@dataclass(frozen=True)
class SelectedDiagramRenderError(RuntimeError):
    code: str
    message: str
    item_id: str | None = None

    def __str__(self) -> str:
        return self.message


def render_selected_tikz_candidate(
    task_store: TaskStore,
    asset_store: AssetStore,
    task_id: str,
    *,
    force: bool = False,
) -> TaskRecord:
    """Ensure the selected candidate has one authoritative same-source render bundle."""

    task = task_store.get(task_id)
    if not task.diagram_items:
        raise SelectedDiagramRenderError(
            "diagram_item_not_found",
            "题目没有可重渲染的题图",
        )
    item = task.diagram_items[0]
    if item.active_run_id:
        raise SelectedDiagramRenderError(
            "diagram_run_active",
            "题图重建正在运行",
            item.id,
        )
    candidate = next(
        (candidate for candidate in item.candidates if candidate.id == item.selected_candidate_id),
        None,
    )
    if candidate is None:
        raise SelectedDiagramRenderError(
            "tikz_source_missing",
            "没有可重渲染的 TikZ 源码",
            item.id,
        )
    if candidate.has_normalized_typography_metrics and not force:
        return task

    bundle = TikzRenderClient(asset_store).render(candidate.tikz_source)
    candidates = [
        DiagramCandidate.model_validate(
            {
                **existing.model_dump(),
                "svg_path": bundle.svg_path,
                "pdf_path": bundle.pdf_path,
                "png_path": bundle.png_path,
                "renderer_profile_version": bundle.renderer_profile_version,
                "base_font_size_pt": bundle.base_font_size_pt,
                "canvas_width_em": bundle.canvas_width_em,
                "canvas_height_em": bundle.canvas_height_em,
                "render_error_code": None,
                "render_error_message": None,
            }
        )
        if existing.id == candidate.id
        else existing
        for existing in item.candidates
    ]
    try:
        return task_store.update_diagram_item(
            task_id,
            item.id,
            expected_active_run_id=None,
            candidates=candidates,
            status=DiagramStatus.READY_TIKZ,
            needs_review=False,
            last_error=None,
            last_error_code=None,
        )
    except StateConflict as error:
        raise SelectedDiagramRenderError(
            "diagram_run_active",
            "题图状态已变化，请等待当前重建完成后再试",
            item.id,
        ) from error


__all__ = ["SelectedDiagramRenderError", "render_selected_tikz_candidate"]
