# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys
from abc import ABC, abstractmethod
from copy import deepcopy

from frost_planner.core.base import Machine, SchedulingInstance, Task
from frost_planner.core.objective import ObjectiveWeights
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.solver import (
    _create_schedule,
    _perform_task_interval_allocation,
)


class BaseSolver(ABC):
    """Base class for all scheduling solvers.

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
        machine_intervals: dict[str, list[tuple[int, int]]] | None = None,
        objective: ObjectiveWeights | None = None,
    ) -> None:
        self.instance: SchedulingInstance = instance
        self.horizon: int = horizon
        self.initial_machine_intervals = machine_intervals
        self.objective = objective or ObjectiveWeights()
        self._update_maps()
        self.locked_tasks: dict[str, ScheduledTask] = {}

    def _update_maps(self) -> None:
        """Re-compute internal maps when the instance changes."""
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

    def update_instance(self, instance: SchedulingInstance) -> None:
        """Update the scheduling instance (e.g., when new jobs arrive)."""
        self.instance = instance
        self._update_maps()

    def _create_machine_intervals(
        self, start_time: int = 0
    ) -> dict[str, list[tuple[int, int]]]:
        """Creates the initial availability intervals for each machine."""
        if self.initial_machine_intervals:
            machine_intervals = deepcopy(self.initial_machine_intervals)
        else:
            machine_intervals = {
                machine.id: [(start_time, self.horizon)]
                for machine in self.instance.machines
            }

        # Truncate all intervals to start at least at start_time
        for machine_id in machine_intervals:
            intervals = machine_intervals[machine_id]
            while intervals and intervals[0][1] <= start_time:
                intervals.pop(0)
            if intervals and intervals[0][0] < start_time:
                intervals[0] = (start_time, intervals[0][1])

        for task in self.locked_tasks.values():
            # If the task ends before or at start_time, it's effectively
            # "history" and doesn't consume future machine capacity.
            if task.end_time <= start_time:
                continue

            # If it's active (started < now < end), we must ensure the machine
            # is busy.
            if task.start_time < start_time:
                intervals = machine_intervals[task.machine.id]
                # Machine should be busy from start_time until task.end_time
                if intervals and intervals[0][0] == start_time:
                    new_start = task.end_time
                    if new_start < intervals[0][1]:
                        intervals[0] = (new_start, intervals[0][1])
                    else:
                        intervals.pop(0)
            else:
                # Standard locking for future tasks
                _perform_task_interval_allocation(
                    task.start_time,
                    task.task,
                    task.machine,
                    machine_intervals,
                )
        return machine_intervals

    @abstractmethod
    def _allocate_tasks(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> list[ScheduledTask]:
        """Allocates tasks to machines based on solver strategy."""

    def lock_tasks(self, tasks: list[ScheduledTask] | ScheduledTask) -> None:
        """Locks the specified tasks in the schedule."""
        if isinstance(tasks, ScheduledTask):
            tasks = [tasks]

        for st in tasks:
            self.locked_tasks[st.task.id] = st

    def schedule(self, start_time: int = 0) -> Schedule:
        """Generate a complete schedule, respecting constraints.

        This method handles the overall scheduling process, including merging
        locked tasks with newly scheduled tasks from the solver.

        Args:
            start_time (int):
                The global lower bound for non-locked task start times.

        Returns:
            Schedule:
                The generated schedule with all tasks allocated.
        """
        machine_intervals = self._create_machine_intervals(start_time)

        all_scheduled_tasks = self._allocate_tasks(
            machine_intervals, start_time=start_time
        )

        # Merge logic
        combined_tasks = list(self.locked_tasks.values())
        locked_ids = {st.task.id for st in combined_tasks}

        for st in all_scheduled_tasks:
            if st.task.id not in locked_ids:
                combined_tasks.append(st)

        return _create_schedule(
            scheduled_tasks=combined_tasks,
            machines=self.instance.machines,
        )
