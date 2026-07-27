"""Runtime-specific command, configuration, and event adapters."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Optional
from uuid import uuid4

from oopsnote.mcp.tool_registry import AI_TOOL_NAMES


class RpcRuntimeAdapter(ABC):
    """Base adapter for a JSONL RPC executable."""

    kind: ClassVar[str]
    display_name: ClassVar[str]
    config_dir_name: ClassVar[str]
    default_command: ClassVar[str]
    serialize_startup: ClassVar[bool] = False

    def __init__(self, project_root: Path, model: Optional[str] = None) -> None:
        self.project_root = project_root
        self.config_dir = project_root / self.config_dir_name
        self.config = self._load_config()
        command = self.config.get("command") or [self.default_command]
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) and part for part in command)
        ):
            raise ValueError(
                f"{self.config_dir_name}/runtime.json command must be a "
                "non-empty string array"
            )
        self.command = command
        self.model = (
            model
            or self.config.get("model")
            or os.getenv("OOPSNOTE_AI_MODEL", "deepseek-v4-flash")
        )
        self.provider = self.config.get("provider") or os.getenv(
            "OOPSNOTE_PI_PROVIDER",
            "deepseek",
        )
        self.version = str(self.config.get("version") or "") or None

    @property
    def runtime_path(self) -> Path:
        return self.config_dir / "runtime.json"

    def _load_config(self) -> dict[str, Any]:
        if not self.runtime_path.exists():
            return {}
        try:
            data = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Invalid {self.display_name} runtime config: {self.runtime_path}"
            ) from error
        if not isinstance(data, dict):
            raise ValueError(
                f"{self.config_dir_name}/runtime.json must contain a JSON object"
            )
        return data

    def build_command(self, task_id: str, run_id: str) -> list[str]:
        del task_id, run_id
        return [
            *self.command,
            "--mode",
            "rpc",
            *self.restricted_cli_args(),
            "--provider",
            self.provider,
            "--model",
            self.model,
            *self.extension_cli_args(),
        ]

    @abstractmethod
    def restricted_cli_args(self) -> list[str]:
        """Return the runtime's restricted capability flags."""
        ...

    def extension_cli_args(self) -> list[str]:
        return []

    def configure_child_environment(self, values: dict[str, str]) -> None:
        """Observe ephemeral runtime values before the next worker starts."""
        del values

    def build_environment(self) -> dict[str, str]:
        """Return runtime-specific environment overrides for a child process."""
        return {}

    def cleanup(self) -> None:
        """Remove runtime-owned ephemeral configuration."""

    @abstractmethod
    def is_settled_event(self, event: dict[str, Any]) -> bool:
        """Identify the runtime event that closes an agent turn."""
        ...

    @property
    def startup_lock_name(self) -> str:
        return f".{self.kind}-startup.lock"


class PiRuntimeAdapter(RpcRuntimeAdapter):
    """Adapter for the upstream Pi coding agent."""

    kind = "pi"
    display_name = "Pi"
    config_dir_name = ".pi"
    default_command = "pi"
    serialize_startup = True

    def __init__(self, project_root: Path, model: Optional[str] = None) -> None:
        super().__init__(project_root, model=model)
        self._managed_mcp_config_path: Optional[Path] = None

    def restricted_cli_args(self) -> list[str]:
        return ["--no-builtin-tools", "--no-extensions"]

    def extension_cli_args(self) -> list[str]:
        args: list[str] = []
        mcp_adapter = self.config_dir / "node_modules" / "pi-mcp-adapter" / "index.ts"
        if mcp_adapter.exists():
            args.extend(["--extension", str(mcp_adapter)])
            if self._managed_mcp_config_path is not None:
                args.extend(["--mcp-config", str(self._managed_mcp_config_path)])
        return args

    def configure_child_environment(self, values: dict[str, str]) -> None:
        url = values.get("OOPSNOTE_MCP_URL")
        token = values.get("OOPSNOTE_MCP_TOKEN")
        if not url or not token:
            raise ValueError("Managed upstream Pi requires MCP URL and token")
        runtime_dir = self.project_root / "storage" / "runs"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        if self._managed_mcp_config_path is None:
            self._managed_mcp_config_path = (
                runtime_dir / f".pi-mcp-{os.getpid()}-{uuid4().hex}.json"
            )
        payload = {
            "mcpServers": {
                "oopsnote_pipeline": {
                    "url": url,
                    "headers": {"Authorization": f"Bearer {token}"},
                    "lifecycle": "eager",
                    "directTools": list(AI_TOOL_NAMES),
                }
            }
        }
        self._managed_mcp_config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def managed_mcp_config_path(self) -> Optional[Path]:
        return self._managed_mcp_config_path

    def cleanup(self) -> None:
        path = self._managed_mcp_config_path
        self._managed_mcp_config_path = None
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def is_settled_event(self, event: dict[str, Any]) -> bool:
        return event.get("type") == "agent_settled"


class RustPiRuntimeAdapter(RpcRuntimeAdapter):
    """Adapter for the project-local pi_agent_rust binary."""

    kind = "pi-rust"
    display_name = "pi_agent_rust"
    config_dir_name = ".pi-rust"
    default_command = ".pi-rust/bin/pi.exe"

    def __init__(self, project_root: Path, model: Optional[str] = None) -> None:
        super().__init__(project_root, model=model)
        self._mcp_url: Optional[str] = None
        self._mcp_token: Optional[str] = None

    def restricted_cli_args(self) -> list[str]:
        return [
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-migrations",
            "--extension-policy",
            "permissive",
            "--max-tool-iterations",
            "24",
        ]

    def extension_cli_args(self) -> list[str]:
        bridge = self.config_dir / "extensions" / "oopsnote_mcp.js"
        args = ["--extension", str(bridge)] if bridge.exists() else []
        if self._mcp_url and self._mcp_token:
            args.extend(
                [
                    "--oopsnote-mcp-url",
                    self._mcp_url,
                    "--oopsnote-mcp-token",
                    self._mcp_token,
                ]
            )
        return args

    def configure_child_environment(self, values: dict[str, str]) -> None:
        self._mcp_url = values.get("OOPSNOTE_MCP_URL")
        self._mcp_token = values.get("OOPSNOTE_MCP_TOKEN")

    def build_environment(self) -> dict[str, str]:
        configured_agent = self.config.get("agent_dir")
        configured_sessions = self.config.get("sessions_dir")
        agent_dir = (
            Path(str(configured_agent))
            if configured_agent
            else self.config_dir / "agent"
        )
        sessions_dir = (
            Path(str(configured_sessions))
            if configured_sessions
            else self.config_dir / "sessions"
        )
        if not agent_dir.is_absolute():
            agent_dir = self.project_root / agent_dir
        if not sessions_dir.is_absolute():
            sessions_dir = self.project_root / sessions_dir
        return {
            "PI_CODING_AGENT_DIR": str(agent_dir.resolve()),
            "PI_SESSIONS_DIR": str(sessions_dir.resolve()),
            "PI_HTTP_ALLOW_LOOPBACK": "1",
        }

    def is_settled_event(self, event: dict[str, Any]) -> bool:
        return event.get("type") == "agent_end"
