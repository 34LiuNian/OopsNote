"""Durable identity carried by every managed AI queue item."""

from __future__ import annotations

from dataclasses import dataclass

from oopsnote.core.models import RunPurpose
from oopsnote.core.workspace import WorkspaceId


@dataclass(frozen=True, slots=True)
class ManagedWorkItem:
    workspace_id: WorkspaceId
    task_id: str
    run_id: str
    purpose: RunPurpose
    quota_reservation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", WorkspaceId.parse(self.workspace_id))
        if not isinstance(self.purpose, RunPurpose):
            object.__setattr__(self, "purpose", RunPurpose(self.purpose))
        for field_name in ("task_id", "run_id", "quota_reservation_id"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
