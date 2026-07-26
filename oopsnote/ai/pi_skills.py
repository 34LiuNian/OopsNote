"""Load the repository-owned Pi skill pack for a clean Pi RPC session."""

from __future__ import annotations

import hashlib
from pathlib import Path


# Auto segmentation is intentionally excluded: Web tasks are already cropped.
ACTIVE_PI_SKILLS = (
    "oopsnote-orchestrator",
    "oopsnote-ocr-extract",
    "oopsnote-solve-problem",
    "oopsnote-tag-problem",
)


def _instruction_body(source: str) -> str:
    """Drop repository metadata that has no runtime instruction value."""

    if source.startswith("---\n"):
        _, separator, body = source[4:].partition("\n---\n")
        if separator:
            return body.lstrip()
    return source


def load_skill_pack(project_root: Path) -> str:
    """Return the synced skills in a prompt-safe, deterministic form.

    Pi's project skill auto-discovery is version-dependent. Passing this pack
    with every clean task session keeps the workflow deterministic.
    """
    skill_root = project_root / "skills"
    sections: list[str] = []
    missing: list[str] = []
    for name in ACTIVE_PI_SKILLS:
        path = skill_root / name / "SKILL.md"
        if not path.exists():
            missing.append(name)
            continue
        source = _instruction_body(path.read_text(encoding="utf-8"))
        sections.append(f"<skill name=\"{name}\">\n{source}\n</skill>")
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
                f"Pi skills are not synced: {joined}. "
            "Restore the missing repository skill sources."
        )
    return "\n\n".join(sections)


def skill_pack_version(skill_pack: str) -> str:
    """Return a content-derived identifier for persisted run diagnostics."""

    digest = hashlib.sha256(skill_pack.encode("utf-8")).hexdigest()[:16]
    return f"oopsnote-skills-sha256:{digest}"
