"""
Background Task Manager for LLM2LLM-Bridge

This module provides centralized tracking of background tasks
to ensure proper cleanup during shutdown.
"""

import asyncio
import logging
from typing import Set, Optional, Callable
from weakref import WeakSet
import uuid

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Manages background tasks and ensures they are properly tracked
    and cleaned up during shutdown.
    """
    
    def __init__(self):
        # Use WeakSet to automatically remove completed tasks
        self._tasks: WeakSet[asyncio.Task] = WeakSet()
        self._shutdown_in_progress = False
        
    def create_task(
        self, 
        coro, 
        *, 
        name: Optional[str] = None,
        error_handler: Optional[Callable[[Exception], None]] = None
    ) -> asyncio.Task:
        """
        Create and track a background task.
        
        Args:
            coro: The coroutine to run
            name: Optional name for the task
            error_handler: Optional callback for handling exceptions
            
        Returns:
            The created task
        """
        if self._shutdown_in_progress:
            logger.warning("Attempted to create task during shutdown, ignoring")
            # Return a cancelled task
            task = asyncio.create_task(self._noop())
            task.cancel()
            return task
            
        # Generate a unique name if not provided
        if not name:
            name = f"background-task-{uuid.uuid4().hex[:8]}"
            
        # Create the task
        task = asyncio.create_task(coro, name=name)
        
        # Add to tracking set
        self._tasks.add(task)
        
        # Add done callback for logging
        task.add_done_callback(self._task_done_callback)
        
        # Add error handler if provided
        if error_handler:
            task.add_done_callback(
                lambda t: error_handler(t.exception()) if t.exception() else None
            )
            
        logger.debug(f"Created background task: {name}")
        return task
        
    def _task_done_callback(self, task: asyncio.Task):
        """Callback when a task completes"""
        try:
            if task.exception():
                logger.error(
                    f"Background task '{task.get_name()}' failed with exception",
                    exc_info=task.exception()
                )
            else:
                logger.debug(f"Background task '{task.get_name()}' completed successfully")
        except asyncio.CancelledError:
            logger.debug(f"Background task '{task.get_name()}' was cancelled")
            
    async def _noop(self):
        """No-op coroutine for cancelled tasks"""
        pass
        
    async def shutdown(self, timeout: float = 10.0) -> int:
        """
        Shutdown all tracked tasks gracefully.
        
        Args:
            timeout: Maximum time to wait for tasks to complete
            
        Returns:
            Number of tasks that were cancelled
        """
        self._shutdown_in_progress = True
        
        # Get all pending tasks
        pending_tasks = [t for t in self._tasks if not t.done()]
        
        if not pending_tasks:
            logger.info("No background tasks to shutdown")
            return 0
            
        logger.info(f"Shutting down {len(pending_tasks)} background tasks...")
        
        # Cancel all tasks
        for task in pending_tasks:
            task.cancel()
            
        # Wait for tasks to complete with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending_tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.info(f"All {len(pending_tasks)} tasks completed shutdown")
        except asyncio.TimeoutError:
            still_pending = [t for t in pending_tasks if not t.done()]
            logger.warning(
                f"{len(still_pending)} tasks did not complete within "
                f"{timeout}s timeout and were forcefully cancelled"
            )
            
        return len(pending_tasks)
        
    @property
    def active_task_count(self) -> int:
        """Get the number of currently active tasks"""
        return len([t for t in self._tasks if not t.done()])
        
    def get_task_info(self) -> list[dict]:
        """Get information about all tracked tasks"""
        info = []
        for task in self._tasks:
            has_exception = False
            if task.done() and not task.cancelled():
                try:
                    has_exception = task.exception() is not None
                except:
                    pass
                    
            info.append({
                "name": task.get_name(),
                "done": task.done(),
                "cancelled": task.cancelled(),
                "has_exception": has_exception
            })
        return info


# Global task manager instance
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get the global task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


def create_background_task(
    coro,
    *,
    name: Optional[str] = None,
    error_handler: Optional[Callable[[Exception], None]] = None
) -> asyncio.Task:
    """
    Convenience function to create a tracked background task.
    
    This is a drop-in replacement for asyncio.create_task() that
    ensures the task is properly tracked and cleaned up.
    """
    return get_task_manager().create_task(coro, name=name, error_handler=error_handler)