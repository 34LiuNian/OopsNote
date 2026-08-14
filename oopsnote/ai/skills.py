"""Load the repository-owned managed AI skill pack deterministically."""

from __future__ import annotations

import hashlib
from pathlib import Path

# Auto segmentation is intentionally excluded: Web tasks are already cropped.
ACTIVE_AI_SKILLS = (
    "oopsnote-orchestrator",
    "oopsnote-ocr-extract",
    "oopsnote-solve-problem",
    "oopsnote-tag-problem",
)


def _instruction_body(source: str) -> str:
    if source.startswith("---\n"):
        _, separator, body = source[4:].partition("\n---\n")
        if separator:
            return body.lstrip()
    return source


def load_skill_pack(project_root: Path) -> str:
    """Return the canonical skills in a prompt-safe, deterministic form."""
    skill_root = project_root / "skills"
    sections: list[str] = []
    missing: list[str] = []
    for name in ACTIVE_AI_SKILLS:
        path = skill_root / name / "SKILL.md"
        if not path.exists():
            missing.append(name)
            continue
        source = _instruction_body(path.read_text(encoding="utf-8"))
        sections.append(f'<skill name="{name}">\n{source}\n</skill>')
    if missing:
        raise RuntimeError(
            f"AI skills are unavailable: {', '.join(missing)}. "
            "Restore the missing repository skill sources."
        )
    return "\n\n".join(sections)


def skill_pack_version(skill_pack: str) -> str:
    digest = hashlib.sha256(skill_pack.encode("utf-8")).hexdigest()[:16]
    return f"oopsnote-skills-sha256:{digest}"


__all__ = ["ACTIVE_AI_SKILLS", "load_skill_pack", "skill_pack_version"]
