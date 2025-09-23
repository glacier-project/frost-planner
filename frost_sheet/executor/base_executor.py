from abc import ABC, abstractmethod
from typing import Callable, Optional
from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.core.base import SchedulingInstance, Task, TaskStatus, Machine
from frost_sheet.solver.base_solver import BaseSolver

class BaseExecutor(ABC):
    """Base executor class for managing task execution and schedule updates.
    
    Attributes:
        solver (BaseSolver): The solver used to generate the schedule.
        instance (SchedulingInstance): The scheduling instance containing jobs and machines.
    """
    
    def __init__(self, solver: BaseSolver, instance: SchedulingInstance):
        self.solver = solver
        self.instance = instance
        self.schedule: Schedule | None = None

    @abstractmethod
    def update_schedule(self) -> Schedule:
        """Update and return the current schedule."""
        pass

    @abstractmethod
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
        self._update_task_status()

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

    def _update_task_status(self) -> None:
        """Update the status of all tasks in the schedule."""
        schedule = self.get_current_schedule()
        
        for machine_tasks in schedule.mapping.values():
            for scheduled_task in machine_tasks:
                if scheduled_task.task.status != TaskStatus.WAITING:
                    continue

                if schedule.can_start(scheduled_task):
                    scheduled_task.task.status = TaskStatus.READY

    def next_ready_tasks(self) -> list[tuple[ScheduledTask, Machine]]:
        """Return the next tasks that are ready to be executed on each machine."""
        schedule = self.update_schedule()

        ready_tasks: list[tuple[ScheduledTask, Machine]] = []
        for machine in self.instance.machines:
            scheduled_tasks = schedule.get_machine_tasks(machine)

            # Find the next task that is ready to be executed
            for task in scheduled_tasks:
                if task.task.status == TaskStatus.READY:
                    ready_tasks.append((task, machine))
                    break

        return ready_tasks