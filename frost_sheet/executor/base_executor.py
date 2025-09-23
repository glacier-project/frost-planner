from abc import ABC, abstractmethod
from typing import Callable, Optional
from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.core.base import SchedulingInstance, Task, TaskStatus, Machine
from frost_sheet.solver.base_solver import BaseSolver

class BaseExecutor(ABC):
    """Base executor class for managing task execution and schedule updates.
    
    Attributes:
        solver (BaseSolver): The solver used to generate the schedule.
    """
    
    def __init__(self, solver: BaseSolver):
        self.solver = solver
        self.schedule: Schedule | None = None
        self.update_task_status()

    @abstractmethod
    def update_schedule(self) -> Schedule:
        """Update and return the current schedule."""
        pass

    def get_current_schedule(self) -> Schedule:
        """Get the current schedule."""
        if self.schedule is None:
            self.schedule = self.update_schedule()

        return self.schedule

    def task_completed(self, scheduled_task: ScheduledTask) -> None:
        """Mark a task as completed and update the schedule accordingly.
        
        Args:
            scheduled_task (ScheduledTask): The task that has been completed.
        """
        scheduled_task.task.status = TaskStatus.COMPLETED

    def task_failed(self, scheduled_task: ScheduledTask) -> None:
        """Mark a task as failed and update the schedule accordingly.

        Args:
            scheduled_task (ScheduledTask): The task that has failed.
        """
        scheduled_task.task.status = TaskStatus.FAILED

    def task_started(self, scheduled_task: ScheduledTask) -> None:
        """Mark a task as restarted and update the schedule accordingly.
        
        Args:
            scheduled_task (ScheduledTask): The task that has started.
        """
        scheduled_task.task.status = TaskStatus.IN_PROGRESS

    def update_task_status(self) -> None:
        """Update the status of all tasks in the schedule."""

        instance = self.solver.instance
        for job in instance.jobs:
            for task in job.tasks:
                if task.status != TaskStatus.WAITING:
                    continue

                if len(task.dependencies) == 0:
                    task.status = TaskStatus.READY
                    continue
                
                for dependency in task.dependencies:
                    predecessor_task = job.find_task(dependency)
                    assert predecessor_task is not None, f"Dependency task with ID {dependency} not found in job {job.id}."

                    if predecessor_task.status != TaskStatus.COMPLETED:
                        break
                    task.status = TaskStatus.READY


    def next_ready_tasks(self) -> list[tuple[ScheduledTask, Machine]]:
        """Return the next tasks that are ready to be executed on each machine."""
        schedule = self.get_current_schedule()
        instance = self.solver.instance

        ready_tasks: list[tuple[ScheduledTask, Machine]] = []
        for machine in instance.machines:
            scheduled_tasks = schedule.get_machine_tasks(machine)

            # Find the next task that is ready to be executed
            for task in scheduled_tasks:
                if task.task.status == TaskStatus.READY:
                    ready_tasks.append((task, machine))
                    break

        return ready_tasks