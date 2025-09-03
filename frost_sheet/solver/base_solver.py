import sys
from abc import ABC, abstractmethod
from frost_sheet.core.base import Task, Machine, SchedulingInstance
from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.solver import _create_schedule, _perform_task_interval_allocation


class BaseSolver(ABC):
    """
    Base class for all scheduling solvers.

    Attributes:
        instance (SchedulingInstance):
            The scheduling instance containing jobs and machines.
        horizon (int):
            The time horizon for the scheduling.
    """

    def __init__(
        self,
        instance: SchedulingInstance,
        horizon: int = sys.maxsize,
    ) -> None:
        self.instance: SchedulingInstance = instance
        self.horizon: int = horizon
        # Add pre-computed maps.
        self.machine_id_map: dict[str, Machine] = {
            m.id: m for m in self.instance.machines
        }
        self.task_id_map: dict[str, Task] = {
            t.id: t for job in self.instance.jobs for t in job.tasks
        }
        self.suitable_machines_map: dict[str, list[Machine]] = {
            t.id: self.instance.get_suitable_machines(t)
            for job in self.instance.jobs
            for t in job.tasks
        }

    def _create_machine_intervals(self) -> dict[str, list[tuple[int, int]]]:
        """
        Creates the initial availability intervals for each machine.

        Returns:
            dict[str, list[tuple[int, int]]]:
                A dictionary mapping machine IDs to their availability
                intervals.
        """
        return {machine.id: [(0, self.horizon)] for machine in self.instance.machines}

    def _allocate_task(
        self,
        start_time: int,
        task: Task,
        machine: Machine,
        machine_intervals: dict[str, list[tuple[int, int]]],
    ) -> ScheduledTask:
        """
        Allocates a task to a machine at a specific start time.

        Args:
            start_time (int):
                The start time for the task allocation.
            task (Task):
                The task to allocate.
            machine (Machine):
                The machine to allocate the task to.
            machine_intervals (dict[str, list[tuple[int, int]]]):
                The availability intervals for each machine.

        Returns:
            ScheduledTask:
                The scheduled task after allocation.
        """
        _perform_task_interval_allocation(start_time, task, machine, machine_intervals)
        return ScheduledTask(
            start_time=start_time,
            end_time=start_time + task.processing_time,
            task=task,
            machine=machine,
        )

    @abstractmethod
    def _allocate_tasks(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
    ) -> list[ScheduledTask]:
        """
        Allocates tasks to machines based on solver strategy.

        Args:
            machine_intervals (dict[int, list[tuple[int, int]]]):
                The availability intervals for each machine.
        Returns:
            list[ScheduledTask]:
                The scheduled tasks after allocation.
        """
        pass

    def schedule(self) -> Schedule:
        """
        Schedules the tasks on the machines.

        This method should be implemented by subclasses to provide specific
        scheduling algorithms.

        Returns:
            Schedule:
                The schedule created by the scheduling algorithm.
        """
        machine_intervals = self._create_machine_intervals()
        scheduled_tasks = self._allocate_tasks(machine_intervals)

        # create schedule from scheduled_tasks.
        return _create_schedule(
            scheduled_tasks=scheduled_tasks,
            machines=self.instance.machines,
        )
