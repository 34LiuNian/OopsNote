"""Install, sync, and validate the project-local pi_agent_rust runtime.

Usage:
  python scripts/setup/setup_pi_rust.py
  python scripts/setup/setup_pi_rust.py --sync
  python scripts/setup/setup_pi_rust.py --install --sync
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from oopsnote.ai import PiRpcBackend
from oopsnote.mcp.restricted import AI_TOOL_NAMES


ROOT = Path(__file__).resolve().parents[2]
PI_RUST_VERSION = "0.1.22"
PI_RUST_WINDOWS_X64_URL = (
    "https://github.com/Dicklesworthstone/pi_agent_rust/releases/download/"
    f"v{PI_RUST_VERSION}/pi-{PI_RUST_VERSION}-x86_64-pc-windows-msvc.zip"
)
PI_RUST_WINDOWS_X64_ZIP_SHA256 = (
    "6486c6fe78c484b8be61360e9c96f91426efc2b9bb493696fab3ccd088e43ba3"
)
PI_RUST_WINDOWS_X64_EXE_SHA256 = (
    "e898f4732ce139ea5cfaf41bb41ab792a58007ab626a657cd830c407a8d4ec51"
)
PI_RUST_BINARY = ROOT / ".pi-rust" / "bin" / "pi.exe"
EXPECTED_TOOLS = {
    "ocr_image",
    "get_task",
    "get_asset_path",
    "list_tags",
    "create_tag",
    "report_task_stage",
    "finalize_task",
    "fail_task",
}


def check(condition: bool, label: str) -> bool:
    print(f"[{'ok' if condition else 'missing'}] {label}")
    return condition


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_binary() -> None:
    PI_RUST_BINARY.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oopsnote-pi-rust-") as temp_name:
        temp_dir = Path(temp_name)
        archive = temp_dir / "pi-rust.zip"
        print(f"Downloading pi_agent_rust v{PI_RUST_VERSION} ...")
        with urllib.request.urlopen(PI_RUST_WINDOWS_X64_URL, timeout=900) as response:
            with archive.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        actual_archive = sha256(archive)
        if actual_archive != PI_RUST_WINDOWS_X64_ZIP_SHA256:
            raise RuntimeError(
                "pi_agent_rust archive checksum mismatch: "
                f"expected {PI_RUST_WINDOWS_X64_ZIP_SHA256}, got {actual_archive}"
            )
        with zipfile.ZipFile(archive) as bundle:
            candidates = [name for name in bundle.namelist() if Path(name).name == "pi.exe"]
            if len(candidates) != 1:
                raise RuntimeError("pi_agent_rust archive must contain exactly one pi.exe")
            extracted = temp_dir / "pi.exe"
            with bundle.open(candidates[0]) as source, extracted.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
        actual_binary = sha256(extracted)
        if actual_binary != PI_RUST_WINDOWS_X64_EXE_SHA256:
            raise RuntimeError(
                "pi_agent_rust binary checksum mismatch: "
                f"expected {PI_RUST_WINDOWS_X64_EXE_SHA256}, got {actual_binary}"
            )
        shutil.copy2(extracted, PI_RUST_BINARY)


def sync_local_config() -> None:
    config_dir = ROOT / ".pi-rust"
    config_dir.mkdir(parents=True, exist_ok=True)
    runtime = config_dir / "runtime.json"
    if not runtime.exists():
        shutil.copy2(config_dir / "runtime.json.example", runtime)
        print("[sync] .pi-rust/runtime.json")

    # pi_agent_rust understands Pi's auth.json format, but gets a separate
    # project-local copy so neither runtime mutates the other's state.
    source_auth = Path.home() / ".pi" / "agent" / "auth.json"
    target_auth = config_dir / "agent" / "auth.json"
    if source_auth.exists():
        target_auth.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_auth, target_auth)
        print("[sync] Pi auth -> .pi-rust/agent/auth.json")


def validate() -> bool:
    valid = True
    valid &= check(PI_RUST_BINARY.exists(), f"pi_agent_rust binary: {PI_RUST_BINARY}")
    if PI_RUST_BINARY.exists():
        valid &= check(
            sha256(PI_RUST_BINARY) == PI_RUST_WINDOWS_X64_EXE_SHA256,
            "pi_agent_rust Windows x64 SHA-256",
        )
        try:
            result = subprocess.run(
                [str(PI_RUST_BINARY), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            version = result.stdout.strip() or result.stderr.strip()
            valid &= check(
                result.returncode == 0 and version.startswith(f"pi {PI_RUST_VERSION} "),
                f"pi_agent_rust version: {version}",
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            valid &= check(False, f"pi_agent_rust version check: {error}")

    try:
        backend = PiRpcBackend(ROOT, runtime="pi-rust")
        command = backend.build_command("setup", "setup")
        environment = backend.build_environment()
        valid &= check(backend.runtime_kind == "pi-rust", "Rust runtime adapter")
        valid &= check("--no-tools" in command, "Rust built-in tools disabled")
        valid &= check("--no-extensions" in command, "Rust auto extensions disabled")
        valid &= check("--no-skills" in command, "Rust skill discovery disabled")
        valid &= check(
            str(ROOT / ".pi-rust" / "extensions" / "oopsnote_mcp.js") in command,
            "Rust restricted MCP bridge loaded explicitly",
        )
        valid &= check(
            environment.get("PI_CODING_AGENT_DIR")
            == str((ROOT / ".pi-rust" / "agent").resolve()),
            "Rust project-local agent directory",
        )
    except (OSError, ValueError) as error:
        valid &= check(False, f"pi_agent_rust runtime config: {error}")

    valid &= check(set(AI_TOOL_NAMES) == EXPECTED_TOOLS, "exact eight-tool surface")
    valid &= check(
        (ROOT / ".pi-rust" / "extensions" / "oopsnote_mcp.js").exists(),
        "Rust MCP bridge extension",
    )
    auth_path = ROOT / ".pi-rust" / "agent" / "auth.json"
    if auth_path.exists():
        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            valid &= check(bool(auth.get("deepseek", {}).get("key")), "Rust DeepSeek auth")
        except (OSError, json.JSONDecodeError):
            valid &= check(False, "read .pi-rust/agent/auth.json")
    else:
        valid &= check(False, ".pi-rust/agent/auth.json (run --sync)")
    return valid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    if args.install:
        install_binary()
    if args.sync:
        sync_local_config()
    return 0 if validate() else 1


if __name__ == "__main__":
    sys.exit(main())
