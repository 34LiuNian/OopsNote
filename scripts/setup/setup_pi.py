"""Validate & sync Pi configuration for OopsNote.

Usage:
  python scripts/setup/setup_pi.py              # validate only
  python scripts/setup/setup_pi.py --sync       # sync skills into .pi/skills/
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from oopsnote.ai import PiRpcBackend
from oopsnote.ai.skills import ACTIVE_AI_SKILLS

ACTIVE_PI_SKILLS = ACTIVE_AI_SKILLS
from oopsnote.ai.rpc.probe import probe_new_session
from oopsnote.mcp.contracts import AI_TOOL_NAMES
from oopsnote.mcp.http_runtime import SharedMcpHttpRuntime

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PIPELINE_TOOLS = set(AI_TOOL_NAMES)


def check(condition: bool, label: str) -> bool:
    print(f"[{'ok' if condition else 'missing'}] {label}")
    return condition


def sync_skills() -> int:
    """Mirror the active repository skills into Pi's project directory."""
    src_root = ROOT / "skills"
    dst_root = ROOT / ".pi" / "skills"
    copied = 0
    for name in ACTIVE_PI_SKILLS:
        src = src_root / name
        if not src.exists():
            print(f"  [skip] {name}: source not found")
            continue
        dst = dst_root / name
        if not (src / "SKILL.md").exists():
            print(f"  [skip] {name}: SKILL.md not found")
            continue
        shutil.copytree(src, dst, dirs_exist_ok=True)
        copied += 1
        print(f"  [sync] {name} -> .pi/skills/{name}/")
    return copied


def check_skills_synced() -> bool:
    """Check that Pi runs exactly the skill files tracked in this repository."""
    valid = True
    for name in ACTIVE_PI_SKILLS:
        src = ROOT / "skills" / name / "SKILL.md"
        dst = ROOT / ".pi" / "skills" / name / "SKILL.md"
        same = src.exists() and dst.exists() and src.read_bytes() == dst.read_bytes()
        valid &= check(same, f"Pi skill synced: {name}")
    return valid


def check_rpc_startup() -> bool:
    """Start a clean upstream session against the real restricted MCP transport."""

    runtime = SharedMcpHttpRuntime()
    backend = None
    try:
        mcp_environment = runtime.start()
        backend = PiRpcBackend(ROOT, runtime="pi")
        backend.runtime.configure_child_environment(mcp_environment)
        managed_config_path = backend.runtime.managed_mcp_config_path
        managed_config = json.loads(managed_config_path.read_text(encoding="utf-8"))
        configured = set(managed_config["mcpServers"]["oopsnote_pipeline"]["directTools"])
        surface_valid = check(
            configured == REQUIRED_PIPELINE_TOOLS,
            "ephemeral upstream MCP whitelist matches expected tools",
        )
        environment = os.environ.copy()
        environment.update(mcp_environment)
        result = probe_new_session(
            backend.build_command("setup", "setup"),
            cwd=ROOT,
            environment=environment,
            timeout_seconds=30,
        )
        detail = "" if result.success else result.failure_detail
        return surface_valid and check(
            result.success,
            "upstream Pi restricted MCP startup" + (f": {detail}" if detail else ""),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return check(False, f"upstream Pi restricted MCP startup: {error}")
    finally:
        if backend is not None:
            backend.runtime.cleanup()
        runtime.shutdown()


def main() -> int:
    runtime_path = ROOT / ".pi" / "runtime.json"
    command_parts = [os.getenv("OOPSNOTE_PI_COMMAND", "pi")]
    if runtime_path.exists():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            configured = runtime.get("command") if isinstance(runtime, dict) else None
            if (
                isinstance(configured, list)
                and configured
                and all(isinstance(part, str) and part for part in configured)
            ):
                command_parts = configured
            else:
                raise ValueError("command must be a non-empty string array")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"[missing] read .pi/runtime.json: {error}")
            return 1
    executable = (
        shutil.which(command_parts[0])
        if Path(command_parts[0]).name == command_parts[0]
        else command_parts[0]
    )
    valid = check(bool(executable), f"Pi command: {' '.join(command_parts)}")
    if executable:
        try:
            result = subprocess.run(
                [executable, *command_parts[1:], "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            valid &= check(
                result.returncode == 0,
                f"Pi version: {result.stdout.strip() or result.stderr.strip()}",
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            valid &= check(False, f"Pi version check: {error}")
    package_path = ROOT / ".pi" / "package.json"
    mcp_path = ROOT / ".pi" / "mcp.json"
    valid &= check(package_path.exists(), ".pi pinned dependencies")
    valid &= check(mcp_path.exists(), "restricted OopsNote MCP config")
    valid &= check(
        bool(runtime_path.exists() or shutil.which("pi")),
        "Pi runtime config (.pi/runtime.json) or pi on PATH",
    )
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        valid &= check(
            package.get("dependencies", {}).get("pi-mcp-adapter") == "2.11.0",
            "pi-mcp-adapter pinned to 2.11.0",
        )
    except (OSError, json.JSONDecodeError):
        valid &= check(False, "read .pi/package.json")
    try:
        mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
        valid &= check(
            mcp.get("mcpServers") == {},
            "project MCP config contains no persistent runtime endpoint",
        )
    except (KeyError, OSError, json.JSONDecodeError):
        valid &= check(False, "read .pi/mcp.json")
    valid &= check_rpc_startup()
    valid &= check_skills_synced()
    ext_cfg_path = ROOT / ".pi" / "extensions.json"
    ext_cfg = {}
    if ext_cfg_path.exists():
        try:
            ext_cfg = json.loads(ext_cfg_path.read_text(encoding="utf-8")).get("ocr_image", {})
            valid &= check(True, "extensions config loaded")
        except (OSError, json.JSONDecodeError):
            valid &= check(False, "read .pi/extensions.json")
    else:
        valid &= check(
            False, ".pi/extensions.json (create manually from .pi/extensions.json.example)"
        )
    valid &= check(
        bool(ext_cfg.get("dashscope_api_key")), "DashScope OCR key (.pi/extensions.json)"
    )
    valid &= check(bool(ext_cfg.get("model")), "OCR model (.pi/extensions.json)")
    pi_auth = Path.home() / ".pi" / "agent" / "auth.json"
    if pi_auth.exists():
        try:
            auth = json.loads(pi_auth.read_text(encoding="utf-8"))
            has_ds = bool(auth.get("deepseek", {}).get("key"))
            valid &= check(has_ds, "DeepSeek key (from Pi local auth.json)")
        except (OSError, json.JSONDecodeError):
            valid &= check(False, "read ~/.pi/agent/auth.json")
    else:
        valid &= check(False, "DeepSeek key - missing Pi local auth.json")
    return 0 if valid else 1


def main_sync() -> int:
    print("Syncing skills to .pi/skills/ ...")
    count = sync_skills()
    print(f"Done: {count} skills synced\n")
    print("Running validation...\n")
    return main()


if __name__ == "__main__":
    if "--sync" in sys.argv:
        sys.exit(main_sync())
    else:
        sys.exit(main())
