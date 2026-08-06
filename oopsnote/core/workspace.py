"""Workspace identity types shared by API, Core, lifecycle, and MCP boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


_REGISTRATION_TOKEN = object()


@dataclass(frozen=True, slots=True)
class Principal:
    """A Better Auth identity already verified by the trusted BFF boundary."""

    user_id: str
    role: UserRole

    def __post_init__(self) -> None:
        normalized = self.user_id.strip()
        if not normalized or len(normalized) > 255:
            raise ValueError("principal user_id must contain 1 to 255 characters")
        object.__setattr__(self, "user_id", normalized)
        if not isinstance(self.role, UserRole):
            try:
                role = UserRole(self.role)
            except ValueError as error:
                raise ValueError("principal role must be admin or user") from error
            object.__setattr__(self, "role", role)


@dataclass(frozen=True, slots=True, order=True)
class WorkspaceId:
    value: UUID

    @classmethod
    def new(cls) -> "WorkspaceId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: object) -> "WorkspaceId":
        if isinstance(value, cls):
            return value
        try:
            return cls(UUID(str(value)))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("workspace_id must be a canonical UUID") from error

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """A registry-derived physical data boundary for exactly one workspace."""

    workspace_id: WorkspaceId
    root: Path
    _registration_token: object = field(default=None, repr=False, compare=False)

    @classmethod
    def _from_registry(
        cls,
        storage_root: Path,
        workspace_id: WorkspaceId,
    ) -> "WorkspaceContext":
        parsed_id = WorkspaceId.parse(workspace_id)
        workspaces_root = (Path(storage_root) / "workspaces").resolve()
        workspaces_root.mkdir(parents=True, exist_ok=True)
        root = (workspaces_root / str(parsed_id)).resolve()
        if root.parent != workspaces_root:
            raise ValueError("workspace root escaped the registered storage boundary")
        root.mkdir(parents=False, exist_ok=True)
        return cls(
            workspace_id=parsed_id,
            root=root,
            _registration_token=_REGISTRATION_TOKEN,
        )

    def __post_init__(self) -> None:
        if self._registration_token is not _REGISTRATION_TOKEN:
            raise ValueError("workspace context must be created by WorkspaceRegistry")
        parsed_id = WorkspaceId.parse(self.workspace_id)
        resolved_root = Path(self.root).resolve()
        if resolved_root.name != str(parsed_id) or resolved_root.parent.name != "workspaces":
            raise ValueError("workspace context must use storage/workspaces/<workspace_id>")
        object.__setattr__(self, "workspace_id", parsed_id)
        object.__setattr__(self, "root", resolved_root)
