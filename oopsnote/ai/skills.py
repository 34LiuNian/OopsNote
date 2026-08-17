"""Load the repository-owned managed AI skill pack deterministically."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from string import Template

import yaml

# Auto segmentation is intentionally excluded: Web tasks are already cropped.
ACTIVE_AI_SKILLS = (
    "oopsnote-orchestrator",
    "oopsnote-solve-problem",
    "oopsnote-tag-problem",
)


class _SkillPromptTemplate(Template):
    delimiter = "@"


def _instruction_body(source: str) -> str:
    if source.startswith("---\n"):
        _, separator, body = source[4:].partition("\n---\n")
        if separator:
            return body.lstrip()
    return source


def _skill_path(project_root: Path, skill_name: str, relative_path: str) -> Path:
    skill_root = (project_root / "skills").resolve()
    path = (skill_root / skill_name / relative_path).resolve()
    if path != skill_root and skill_root not in path.parents:
        raise ValueError("skill prompt path escapes the repository skill root")
    return path


def load_skill_prompt(
    project_root: Path,
    skill_name: str,
    relative_path: str = "SKILL.md",
) -> str:
    """Load one repository-owned prompt source from a skill directory."""

    path = _skill_path(project_root, skill_name, relative_path)
    if not path.is_file():
        raise RuntimeError(f"AI prompt source is unavailable: {path}")
    source = path.read_text(encoding="utf-8")
    return _instruction_body(source) if relative_path == "SKILL.md" else source.strip()


def load_skill_prompts(
    project_root: Path,
    skill_name: str,
    relative_path: str = "prompts.yaml",
) -> dict[str, str]:
    """Load a named prompt collection without allowing prompt text in Python."""

    path = _skill_path(project_root, skill_name, relative_path)
    if not path.is_file():
        raise RuntimeError(f"AI prompt source is unavailable: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError(f"AI prompt collection must be a non-empty mapping: {path}")
    prompts: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"AI prompt collection contains an invalid entry: {path}")
        prompts[key] = value.strip()
    return prompts


def render_skill_prompt(template: str, values: Mapping[str, object] | None = None) -> str:
    """Bind runtime values to a file-owned prompt template."""

    bindings = {key: str(value) for key, value in (values or {}).items()}
    return _SkillPromptTemplate(template).substitute(bindings)


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
        source = load_skill_prompt(project_root, name)
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


__all__ = [
    "ACTIVE_AI_SKILLS",
    "load_skill_pack",
    "load_skill_prompt",
    "load_skill_prompts",
    "render_skill_prompt",
    "skill_pack_version",
]
