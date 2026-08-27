"""Canonical subject identifiers shared by storage adapters and domain services."""

from __future__ import annotations

SUBJECT_ALIASES: dict[str, frozenset[str]] = {
    "math": frozenset({"math", "数学"}),
    "physics": frozenset({"physics", "物理"}),
    "chemistry": frozenset({"chemistry", "化学"}),
    "biology": frozenset({"biology", "生物"}),
    "english": frozenset({"english", "英语"}),
}

_CANONICAL_BY_ALIAS = {
    alias.casefold(): canonical
    for canonical, aliases in SUBJECT_ALIASES.items()
    for alias in aliases
}


def canonical_subject(subject: str | None) -> str | None:
    """Return the stable subject key while preserving unknown subject values."""

    if subject is None:
        return None
    value = subject.strip()
    if not value:
        return value
    return _CANONICAL_BY_ALIAS.get(value.casefold(), value)


def usable_subject(subject: str | None) -> str:
    """Return a catalog-usable subject, treating blank and auto as unset."""

    value = canonical_subject(subject) or ""
    if not value or value == "auto":
        return ""
    return value


def subjects_match(left: str, right: str) -> bool:
    return canonical_subject(left) == canonical_subject(right)


__all__ = ["SUBJECT_ALIASES", "canonical_subject", "subjects_match", "usable_subject"]
