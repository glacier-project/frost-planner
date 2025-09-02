import sys
from abc import ABC, abstractmethod
from frost_sheet.core.base import Task, Machine, SchedulingInstance
from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.solver import _create_schedule


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
        self.instance = instance
        self.horizon = horizon

    def _create_machine_intervals(self) -> dict[str, list[tuple[int, int]]]:
        """
        Creates the initial availability intervals for each machine.

        Returns:
            dict[str, list[tuple[int, int]]]:
                A dictionary mapping machine IDs to their availability
                intervals.
        """
        return {machine.id: [(0, self.horizon)] for machine in self.instance.machines}

    def _get_suitable_machines(self, task: Task) -> list[Machine]:
        """
        Finds all suitable machines for the given task based on its
        requirements.

        Args:
            task (Task): The task to find suitable machines for.

        Returns:
            list[str]: A list of machine IDs that can execute the task.
        """
        suitable_machines = []
        machines = self.instance.machines
        for m in machines:
            for r in task.requires:
                if r in m.capabilities:
                    suitable_machines.append(m)
                    break
        return suitable_machines

    def _set_machines_for_task(
        self, task: Task, machines: list[Machine] | None = None
    ) -> None:
        """
        Sets the machines for a given task.

        Args:
            task (Task):
                The task to set machines for.
            machines (list[Machine] | None):
                The list of machines to assign to the task.
        """
        if machines is None:
            machines = self._get_suitable_machines(task)

        assert all([machine in machines for machine in machines])

        task.machines = [m.id for m in machines]

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
        # find the selected interval
        interval_idx: int = -1
        start: int = 0
        end: int = 0
        for start, end in machine_intervals[machine.id]:
            if start <= start_time and end >= start_time + task.processing_time:
                interval_idx = machine_intervals[machine.id].index((start, end))
                break

        # if the interval is exactly the same as the task's time, remove it
        end_time = start_time + task.processing_time
        if start == start_time and end == end_time:
            machine_intervals[machine.id].pop(interval_idx)
        # if the start of the interval is equal to the task's start time, reduce
        # its length
        elif start == start_time:
            machine_intervals[machine.id][interval_idx] = (end_time, end)
        # if the end of the interval is equal to the task's end time, reduce its
        # length
        elif end == end_time:
            machine_intervals[machine.id][interval_idx] = (start, start_time)
        # if the task is contained within the interval, split the interval
        else:
            machine_intervals[machine.id][interval_idx] = (start, start_time)
            machine_intervals[machine.id].insert(interval_idx + 1, (end_time, end))

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
        tasks = [task for job in self.instance.jobs for task in job.tasks]
        for task in tasks:
            if not task.machines:
                self._set_machines_for_task(task)
        machine_intervals = self._create_machine_intervals()
        scheduled_tasks = self._allocate_tasks(machine_intervals)

        # create schedule from scheduled_tasks.
        return _create_schedule(
            scheduled_tasks=scheduled_tasks,
            machines=self.instance.machines,
        )
