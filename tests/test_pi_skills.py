from __future__ import annotations

from scripts.setup import setup_pi
from oopsnote.ai.pi_skills import ACTIVE_PI_SKILLS, load_skill_pack, skill_pack_version
from oopsnote.mcp.contracts import AI_TOOL_NAMES


def test_sync_skills_mirrors_all_active_skill_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_pi, "ROOT", tmp_path)
    for name in ACTIVE_PI_SKILLS:
        source = tmp_path / "skills" / name
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(f"# {name}\nversion one\n", encoding="utf-8")
    segment = tmp_path / "skills" / "oopsnote-segment"
    segment.mkdir(parents=True)
    (segment / "SKILL.md").write_text("# disabled\n", encoding="utf-8")

    assert setup_pi.sync_skills() == len(ACTIVE_PI_SKILLS)
    assert setup_pi.check_skills_synced()
    assert not (tmp_path / ".pi" / "skills" / "oopsnote-segment").exists()

    changed = tmp_path / "skills" / "oopsnote-solve-problem" / "SKILL.md"
    changed.write_text("# updated solve skill\n", encoding="utf-8")
    assert not setup_pi.check_skills_synced()
    setup_pi.sync_skills()
    assert (tmp_path / ".pi" / "skills" / "oopsnote-solve-problem" / "SKILL.md").read_text(encoding="utf-8") == "# updated solve skill\n"


def test_load_skill_pack_requires_all_active_synced_skills(tmp_path):
    for name in ACTIVE_PI_SKILLS:
        path = tmp_path / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")

    pack = load_skill_pack(tmp_path)

    assert pack.count("<skill name=") == len(ACTIVE_PI_SKILLS)


def test_load_skill_pack_drops_frontmatter_and_empty_knowledge_skeleton(tmp_path):
    for name in ACTIVE_PI_SKILLS:
        path = tmp_path / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {name}\nversion: 1\n---\n\n# Runtime {name}\n",
            encoding="utf-8",
        )

    pack = load_skill_pack(tmp_path)

    assert "version: 1" not in pack
    assert "oopsnote-knowledge" not in ACTIVE_PI_SKILLS
    assert "# Runtime oopsnote-orchestrator" in pack
    assert skill_pack_version(pack).startswith("oopsnote-skills-sha256:")


def test_upstream_pi_uses_the_canonical_restricted_tool_surface():
    assert setup_pi.REQUIRED_PIPELINE_TOOLS == set(AI_TOOL_NAMES)
    assert "ocr_image" in setup_pi.REQUIRED_PIPELINE_TOOLS


def test_setup_pi_reports_a_missing_runtime_without_type_error(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_pi, "ROOT", tmp_path)
    monkeypatch.setattr(setup_pi.shutil, "which", lambda _name: None)
    monkeypatch.setattr(setup_pi, "check_rpc_startup", lambda: False)

    assert setup_pi.main() == 1
