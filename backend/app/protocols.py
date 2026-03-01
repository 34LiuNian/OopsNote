"""
Protocol definitions for dependency injection and interface contracts.

This module defines abstract interfaces (protocols) that implement the
Interface Axiom from the good code principles:
- Separation of Concerns: Interfaces expose only necessary functionality
- Stability: Interfaces are stable and don't change frequently
- Contract Based: Clear types, parameters, and return values
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

from .models import (
    ProblemBlock,
    SolutionBlock,
    TaggingResult,
    TaskCreateRequest,
    TaskRecord,
    AssetMetadata,
    DetectionOutput,
    ArchiveRecord,
    PipelineResult,
)


@runtime_checkable
class AIClient(Protocol):
    """Protocol for AI/LLM client implementations.

    This interface allows swapping different LLM providers without
    changing the business logic that depends on it.
    """

    model: str

    def structured_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """Execute a structured chat completion."""

    def structured_chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        thinking: bool | None = None,
    ) -> dict[str, Any]:
        """Execute a structured chat completion with image input."""


@runtime_checkable
class Extractor(Protocol):
    """Protocol for problem extraction from images."""

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
    ) -> list[ProblemBlock]:
        """Extract problems from uploaded image."""


@runtime_checkable
class Solver(Protocol):
    """Protocol for problem solving."""

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
    ) -> list[SolutionBlock]:
        """Generate solutions for extracted problems."""


@runtime_checkable
class Tagger(Protocol):
    """Protocol for problem tagging."""

    def run(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        solutions: Iterable[SolutionBlock],
    ) -> list[TaggingResult]:
        """Generate tags for solved problems."""


@runtime_checkable
class Archiver(Protocol):
    """Protocol for archiving processed problems."""

    def run(
        self,
        task_id: str,
        problems: Iterable[ProblemBlock],
    ) -> ArchiveRecord:
        """Archive processed problems."""


@runtime_checkable
class Repository(Protocol):
    """Protocol for task persistence."""

    def create_task(self, payload: TaskCreateRequest) -> TaskRecord:
        """Create a new task record."""

    def get_task(self, task_id: str) -> TaskRecord:
        """Retrieve a task by ID."""

    def update_task(self, task: TaskRecord) -> TaskRecord:
        """Update an existing task."""

    def list_tasks(
        self,
        status: str | None = None,
        active_only: bool = False,
        subject: str | None = None,
    ) -> list[TaskRecord]:
        """List tasks with optional filters."""

    def save_pipeline_result(
        self,
        task_id: str,
        result: PipelineResult,
    ) -> None:
        """Save pipeline processing result."""


@runtime_checkable
class EventBus(Protocol):
    """Protocol for event publishing and subscription."""

    def publish(
        self,
        task_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Publish an event for a task."""

    def subscribe(self, task_id: str) -> Iterable[dict[str, Any]]:
        """Subscribe to events for a task."""
