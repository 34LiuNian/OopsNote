"""Load the repository-owned Pi skill pack for a clean Pi RPC session."""

from __future__ import annotations

from pathlib import Path


# Auto segmentation is intentionally excluded: Web tasks are already cropped.
ACTIVE_PI_SKILLS = (
    "oopsnote-orchestrator",
    "oopsnote-ocr-extract",
    "oopsnote-solve-problem",
    "oopsnote-tag-problem",
    "oopsnote-knowledge",
)


def load_skill_pack(project_root: Path) -> str:
    """Return the synced skills in a prompt-safe, deterministic form.

    Pi's project skill auto-discovery is version-dependent. Passing this pack
    with every clean task session keeps the workflow deterministic.
    """
    skill_root = project_root / ".pi" / "skills"
    sections: list[str] = []
    missing: list[str] = []
    for name in ACTIVE_PI_SKILLS:
        path = skill_root / name / "SKILL.md"
        if not path.exists():
            missing.append(name)
            continue
        sections.append(f"<skill name=\"{name}\">\n{path.read_text(encoding='utf-8')}\n</skill>")
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Pi skills are not synced: {joined}. "
            "Run: python scripts/setup/setup_pi.py --sync"
        )
    return "\n\n".join(sections)
