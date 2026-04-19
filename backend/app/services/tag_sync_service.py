from __future__ import annotations

import logging
from typing import Iterable

from ..models import TaggingResult
from ..tags import TagDimension

logger = logging.getLogger(__name__)


class TagSyncService:
    """Centralized tag ref_count synchronization logic.

    This service keeps TasksService focused on workflow orchestration while
    all ref_count mutations are managed in one place.
    """

    def __init__(self, *, tag_store) -> None:
        self.tag_store = tag_store

    @staticmethod
    def _extract_dimension_and_value(tag) -> tuple[TagDimension | None, str | None]:
        dim_key = getattr(tag, "dimension", None)
        value = getattr(tag, "value", None)
        if not dim_key or not value:
            return None, None
        try:
            dim = TagDimension(dim_key) if isinstance(dim_key, str) else dim_key
        except (ValueError, TypeError):
            return None, None
        return dim, str(value)

    def decrement_tagging_results(self, tags: Iterable[TaggingResult]) -> None:
        """Decrease ref_count for the provided tagging results."""
        for tag in tags:
            dim, value = self._extract_dimension_and_value(tag)
            if dim is None or not value:
                continue
            try:
                self.tag_store.update_ref_count_by_value(dim, value, delta=-1)
            except KeyError:
                continue

    def increment_tagging_results(self, tags: Iterable[TaggingResult]) -> None:
        """Increase ref_count for the provided tagging results."""
        for tag in tags:
            dim, value = self._extract_dimension_and_value(tag)
            if dim is None or not value:
                continue
            try:
                self.tag_store.update_ref_count_by_value(dim, value, delta=1)
            except KeyError:
                continue

    def replace_problem_tags(
        self,
        *,
        task_tags: list[TaggingResult],
        problem_id: str,
        new_tags: list[TaggingResult],
    ) -> list[TaggingResult]:
        """Replace tags for one problem with consistent ref_count updates."""
        old_tags = [t for t in (task_tags or []) if t.problem_id == problem_id]
        self.decrement_tagging_results(old_tags)
        self.increment_tagging_results(new_tags)
        return [t for t in (task_tags or []) if t.problem_id != problem_id] + list(new_tags)

    def sync_after_problem_deletion(self, task, problem_id: str) -> None:
        """Decrease ref_count for tags attached to a deleted problem."""
        problem_tags = [t for t in (task.tags or []) if t.problem_id == problem_id]
        self.decrement_tagging_results(problem_tags)

    def sync_after_task_deletion(self, task) -> None:
        """Decrease ref_count for all tags attached to a deleted task."""
        self.decrement_tagging_results(task.tags or [])

    def sync_after_pipeline(
        self,
        *,
        manual_knowledge: list[str],
        manual_error: list[str],
        manual_source: str,
        tags: list[TaggingResult],
    ) -> None:
        """Sync tag store after a full pipeline run.

        Manual tags are counted first. AI tags are then counted with dedup
        against manual knowledge tags.
        """
        manual_knowledge_normalized = {
            str(v).strip().casefold() for v in manual_knowledge if str(v).strip()
        }

        if manual_knowledge or manual_error or manual_source:
            logger.info(
                "Syncing manual tags: knowledge=%s, error=%s, source=%s",
                len(manual_knowledge),
                len(manual_error),
                "yes" if manual_source else "no",
            )

        for val in manual_knowledge:
            self.tag_store.upsert(TagDimension.KNOWLEDGE, val)
            self.tag_store.update_ref_count_by_value(TagDimension.KNOWLEDGE, val, delta=1)

        for val in manual_error:
            self.tag_store.upsert(TagDimension.ERROR, val)
            self.tag_store.update_ref_count_by_value(TagDimension.ERROR, val, delta=1)

        if manual_source:
            self.tag_store.upsert(TagDimension.META, manual_source)
            self.tag_store.update_ref_count_by_value(TagDimension.META, manual_source, delta=1)

        ai_tags_counted = 0
        ai_tags_skipped = 0
        for tag_res in tags:
            for val in tag_res.knowledge_points:
                if str(val).strip().casefold() in manual_knowledge_normalized:
                    ai_tags_skipped += 1
                    continue
                self.tag_store.upsert(TagDimension.KNOWLEDGE, val)
                self.tag_store.update_ref_count_by_value(
                    TagDimension.KNOWLEDGE,
                    val,
                    delta=1,
                )
                ai_tags_counted += 1

        if ai_tags_counted > 0 or ai_tags_skipped > 0:
            logger.info(
                "AI tags processed: counted=%s, skipped=%s",
                ai_tags_counted,
                ai_tags_skipped,
            )
