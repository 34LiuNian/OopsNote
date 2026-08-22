from __future__ import annotations

DEFAULT_PAPER_STRUCTURE: tuple[tuple[str, int, int | tuple[int, ...]], ...] = (
    ("单选题", 8, 5),
    ("多选题", 3, 6),
    ("填空题", 3, 5),
    ("解答题", 5, (13, 15, 15, 17, 17)),
)


def default_points_for(question_type: str, ordinal_within_type: int) -> int | None:
    for current_type, _count, points in DEFAULT_PAPER_STRUCTURE:
        if current_type != question_type:
            continue
        if isinstance(points, tuple):
            return points[ordinal_within_type] if ordinal_within_type < len(points) else points[-1]
        return points
    return None


__all__ = ["DEFAULT_PAPER_STRUCTURE", "default_points_for"]
