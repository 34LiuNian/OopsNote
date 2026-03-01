"""
Domain services for OopsNote backend.

This module contains the core business logic, organized by domain concerns.
Following the Cohesion Axiom: each service focuses on a single responsibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable

from .models import (
    ProblemBlock,
    SolutionBlock,
    TaggingResult,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    AssetMetadata,
    DetectionOutput,
)
from .protocols import (
    Extractor,
    Solver,
    Tagger,
    Archiver,
    Repository,
    EventBus,
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """Context object for task processing pipeline.

    This encapsulates all data needed during processing, making it easy to:
    - Pass data between pipeline stages
    - Add new context fields without changing function signatures
    - Test individual stages in isolation
    """

    task_id: str
    payload: TaskCreateRequest
    asset: AssetMetadata | None = None
    detection: DetectionOutput | None = None
    problems: list[ProblemBlock] = None  # type: ignore[assignment]
    solutions: list[SolutionBlock] = None  # type: ignore[assignment]
    tags: list[TaggingResult] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.problems is None:
            self.problems = []
        if self.solutions is None:
            self.solutions = []
        if self.tags is None:
            self.tags = []


class ExtractionService:
    """Service for extracting problems from images.

    Single Responsibility: Handles all problem extraction logic,
    including OCR and manual reconstruction.
    """

    def __init__(self, extractor: Extractor) -> None:
        self.extractor = extractor

    def extract_problems(
        self,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None = None,
    ) -> tuple[DetectionOutput, list[ProblemBlock]]:
        """Extract problems from uploaded image.

        Args:
            payload: Task creation request with metadata
            asset: Optional asset metadata

        Returns:
            Tuple of (detection result, list of extracted problems)
        """
        # Default detection for single-problem images
        from .models import CropRegion
        from uuid import uuid4

        detection = DetectionOutput(
            action="single",
            regions=[
                CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")
            ],
        )

        problems = self.extractor.run(payload, detection, asset)
        return detection, problems


class SolvingService:
    """Service for generating problem solutions.

    Single Responsibility: Handles all solution generation logic.
    """

    def __init__(self, solver: Solver) -> None:
        self.solver = solver

    def generate_solutions(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[SolutionBlock]:
        """Generate solutions for problems.

        Args:
            payload: Task creation request
            problems: Problems to solve
            on_progress: Optional callback for progress updates

        Returns:
            List of generated solutions
        """
        problems_list = list(problems)
        total = len(problems_list)

        solutions = []
        for idx, problem in enumerate(problems_list, start=1):
            if on_progress:
                on_progress(idx, total)

            # Generate solution for single problem
            problem_solutions = self.solver.run(payload, [problem])
            solutions.extend(problem_solutions)

        return solutions


class TaggingService:
    """Service for tagging problems.

    Single Responsibility: Handles all tagging and categorization logic.
    """

    def __init__(self, tagger: Tagger) -> None:
        self.tagger = tagger

    def generate_tags(
        self,
        payload: TaskCreateRequest,
        problems: Iterable[ProblemBlock],
        solutions: Iterable[SolutionBlock],
    ) -> list[TaggingResult]:
        """Generate tags for solved problems.

        Args:
            payload: Task creation request
            problems: Problems to tag
            solutions: Corresponding solutions

        Returns:
            List of tagging results
        """
        return self.tagger.run(payload, problems, solutions)


class ArchivingService:
    """Service for archiving processed tasks.

    Single Responsibility: Handles all archiving logic.
    """

    def __init__(self, archiver: Archiver) -> None:
        self.archiver = archiver

    def archive_task(
        self,
        task_id: str,
        problems: Iterable[ProblemBlock],
    ):
        """Archive a processed task.

        Args:
            task_id: Task identifier
            problems: Problems to archive

        Returns:
            Archive record
        """
        return self.archiver.run(task_id, problems)


class TaskProcessingService:
    """Orchestrator for complete task processing pipeline.

    Single Responsibility: Coordinates the extraction 鈫?solving 鈫?tagging
    鈫?archiving pipeline without implementing the actual processing logic.

    This follows the Interface Axiom:
    - Depends on abstractions (protocols), not concrete implementations
    - Easy to swap components for testing or different configurations
    """

    def __init__(
        self,
        extraction: ExtractionService,
        solving: SolvingService,
        tagging: TaggingService,
        archiving: ArchivingService,
        repository: Repository,
        event_bus: EventBus,
    ) -> None:
        self.extraction = extraction
        self.solving = solving
        self.tagging = tagging
        self.archiving = archiving
        self.repository = repository
        self.event_bus = event_bus

    def process_task(
        self,
        task_id: str,
        payload: TaskCreateRequest,
        asset: AssetMetadata | None = None,
    ) -> ProcessingContext:
        """Process a task through the complete pipeline.

        Args:
            task_id: Task identifier
            payload: Task creation request
            asset: Optional asset metadata

        Returns:
            Processing context with all results
        """
        context = ProcessingContext(task_id=task_id, payload=payload, asset=asset)

        try:
            # Update status
            from .models import TaskStatus
            
            self.repository.update_task(
                TaskRecord(
                    id=task_id,
                    payload=payload,
                    status=TaskStatus.PROCESSING,
                    created_at=context.payload.image_url,
                    updated_at=context.payload.image_url,
                )
            )

            # Stage 1: Extraction
            self.event_bus.publish(
                task_id,
                "progress",
                {"stage": "extraction", "message": "姝ｅ湪鎻愬彇棰樼洰..."},
            )
            detection, problems = self.extraction.extract_problems(payload, asset)
            context.detection = detection
            context.problems = problems

            # Stage 2: Solving
            self.event_bus.publish(
                task_id, "progress", {"stage": "solving", "message": "姝ｅ湪瑙ｉ..."}
            )
            solutions = self.solving.generate_solutions(
                payload,
                problems,
                on_progress=lambda idx, total: self.event_bus.publish(
                    task_id,
                    "progress",
                    {"stage": "solving", "message": f"瑙ｉ涓?({idx}/{total})..."},
                ),
            )
            context.solutions = solutions

            # Stage 3: Tagging
            self.event_bus.publish(
                task_id, "progress", {"stage": "tagging", "message": "姝ｅ湪鏍囨敞..."}
            )
            tags = self.tagging.generate_tags(payload, problems, solutions)
            context.tags = tags

            # Stage 4: Archiving
            self.event_bus.publish(
                task_id,
                "progress",
                {"stage": "archiving", "message": "姝ｅ湪褰掓。..."},
            )
            self.archiving.archive_task(task_id, problems)

            # Save results
            self.repository.save_pipeline_result(task_id, None)  # type: ignore

            # Mark as completed
            self.event_bus.publish(
                task_id, "progress", {"stage": "completed", "message": "澶勭悊瀹屾垚"}
            )

            return context

        except Exception as e:
            logger.exception("Task processing failed: %s", e)
            self.event_bus.publish(
                task_id, "error", {"stage": "failed", "message": str(e)}
            )
            raise
