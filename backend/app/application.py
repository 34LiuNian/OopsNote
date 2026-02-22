"""
Application services - orchestration layer between API and domain.

This module provides use-case specific services that coordinate domain services
to implement complete business operations. Following the Interface Axiom:
- Clear contracts with well-defined inputs and outputs
- Stable interfaces that don't change frequently
- Separation of concerns from both API and domain layers
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from .models import (
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    UploadRequest,
    AssetMetadata,
    AssetSource,
)
from .protocols import Repository, EventBus
from .domain import (
    TaskProcessingService,
)

logger = logging.getLogger(__name__)


class ApplicationService:
    """Main application service coordinating all use cases.
    
    This class implements the application layer, which:
    - Coordinates domain services to implement use cases
    - Handles transaction boundaries
    - Manages cross-cutting concerns (logging, events)
    - Transforms between API models and domain models
    """
    
    def __init__(
        self,
        repository: Repository,
        event_bus: EventBus,
        processing: TaskProcessingService,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.processing = processing
    
    def create_task(self, payload: TaskCreateRequest) -> TaskRecord:
        """Create a new task.
        
        This is a simple use case that just persists the task without processing.
        
        Args:
            payload: Task creation request
            
        Returns:
            Created task record
        """
        task_id = uuid4().hex
        now = datetime.now(timezone.utc)
        
        task = TaskRecord(
            id=task_id,
            payload=payload,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        
        self.repository.create_task(task)
        logger.info("Task created: %s", task_id)
        
        return task
    
    def upload_task(self, upload: UploadRequest, auto_process: bool = True) -> TaskRecord:
        """Handle image upload and task creation.
        
        This use case:
        1. Converts upload request to task creation request
        2. Creates task record
        3. Optionally triggers immediate processing
        
        Args:
            upload: Upload request with image data
            auto_process: Whether to start processing immediately
            
        Returns:
            Created task record
        """
        # Convert upload to task payload
        payload = TaskCreateRequest(
            image_url=upload.image_url or "data:image/png;base64,placeholder",
            subject=upload.subject,
            grade=upload.grade,
            notes=upload.notes,
            question_no=upload.question_no,
            question_type=upload.question_type,
            mock_problem_count=upload.mock_problem_count,
            difficulty=upload.difficulty,
            source=upload.source,
            knowledge_tags=upload.knowledge_tags,
            error_tags=upload.error_tags,
            user_tags=upload.user_tags,
        )
        
        # Create task
        task = self.create_task(payload)
        
        # Store asset metadata
        asset = AssetMetadata(
            asset_id=uuid4().hex,
            source=AssetSource.UPLOAD if upload.image_base64 else AssetSource.REMOTE,
            original_reference=upload.filename or str(upload.image_url),
            mime_type=upload.mime_type,
            created_at=datetime.now(timezone.utc),
        )
        task.asset = asset
        self.repository.update_task(task)
        
        # Auto-process if requested
        if auto_process:
            self.process_task(task.id)
        
        return task
    
    def process_task(self, task_id: str, background: bool = False) -> TaskRecord:
        """Process a task through the AI pipeline.
        
        This use case:
        1. Retrieves the task
        2. Executes the processing pipeline
        3. Updates task status
        
        Args:
            task_id: Task identifier
            background: Whether to process in background (not implemented)
            
        Returns:
            Updated task record
        """
        task = self.repository.get_task(task_id)
        
        if task.status not in (TaskStatus.PENDING, TaskStatus.FAILED):
            raise ValueError(f"Cannot process task in status: {task.status}")
        
        try:
            # Execute pipeline
            context = self.processing.process_task(
                task_id=task_id,
                payload=task.payload,
                asset=task.asset,
            )
            
            # Update task with results
            task.status = TaskStatus.COMPLETED
            task.detection = context.detection
            task.problems = context.problems
            task.solutions = context.solutions
            task.tags = context.tags
            task.updated_at = datetime.now(timezone.utc)
            
            self.repository.update_task(task)
            logger.info("Task completed: %s", task_id)
            
            return task
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.last_error = str(e)
            task.updated_at = datetime.now(timezone.utc)
            self.repository.update_task(task)
            logger.error("Task failed: %s - %s", task_id, e)
            raise
    
    def get_task(self, task_id: str) -> TaskRecord:
        """Retrieve a task by ID.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task record
        """
        return self.repository.get_task(task_id)
    
    def list_tasks(
        self,
        status: TaskStatus | None = None,
        active_only: bool = False,
        subject: str | None = None,
    ) -> list[TaskRecord]:
        """List tasks with filters.
        
        Args:
            status: Filter by status
            active_only: Filter to only PENDING/PROCESSING tasks
            subject: Filter by subject
            
        Returns:
            List of task records
        """
        return self.repository.list_tasks(
            status=status.value if status else None,
            active_only=active_only,
            subject=subject,
        )
    
    def cancel_task(self, task_id: str) -> TaskRecord:
        """Cancel a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Updated task record
        """
        task = self.repository.get_task(task_id)
        
        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            raise ValueError(f"Cannot cancel task in status: {task.status}")
        
        task.status = TaskStatus.CANCELLED
        task.updated_at = datetime.now(timezone.utc)
        self.repository.update_task(task)
        
        self.event_bus.publish(task_id, "cancelled", {
            "stage": "cancelled",
            "message": "任务已取消"
        })
        
        logger.info("Task cancelled: %s", task_id)
        return task
