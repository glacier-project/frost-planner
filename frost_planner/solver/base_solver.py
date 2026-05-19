# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.objective import (
    ObjectiveWeights,
    calculate_objective_value,
)
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.solver.greedy import (
    _create_schedule,
    _perform_task_interval_allocation,
    _schedule_by_order,
)
from frost_planner.solver.instance_analysis import InstanceAnalysis


@dataclass(frozen=True)
class _GreedyResult:
    """Output of a greedy schedule evaluation."""

    scheduled_tasks: list[ScheduledTask]
    schedule: Schedule
    objective: float


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
        self.locked_tasks: dict[str, ScheduledTask] = {}
        self._update_maps()
        self.analysis = InstanceAnalysis(
            self.instance,
            self.locked_tasks,
            self.suitable_machines_map,
        )

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
        self.analysis = InstanceAnalysis(
            self.instance,
            self.locked_tasks,
            self.suitable_machines_map,
        )

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

    def _greedy_evaluate(
        self,
        jobs: list[Job],
        machine_intervals: dict[str, list[tuple[int, int]]],
        *,
        start_time: int = 0,
        horizon: int | None = None,
        copy_intervals: bool = True,
    ) -> _GreedyResult:
        """Greedy-schedule a job ordering and compute its objective.

        Centralises the four-step (`schedule_by_order` →
        `_create_schedule` → `calculate_objective_value`) sequence
        that every concrete solver runs to evaluate a candidate
        ordering. Locked tasks are honoured automatically. By default
        ``machine_intervals`` is deep-copied so the caller can reuse
        the same input across many evaluations (set
        ``copy_intervals=False`` for one-shot use to avoid the copy).
        """
        locked_tasks_map = {
            st.task.id: st for st in self.locked_tasks.values()
        }
        intervals = (
            deepcopy(machine_intervals)
            if copy_intervals
            else machine_intervals
        )
        scheduled_tasks = _schedule_by_order(
            self.instance,
            jobs,
            intervals,
            horizon=self.horizon if horizon is None else horizon,
            initial_scheduled_tasks=locked_tasks_map,
            min_time=start_time,
            machine_id_map=self.machine_id_map,
            suitable_machines_map=self.suitable_machines_map,
        )
        schedule = _create_schedule(
            scheduled_tasks=scheduled_tasks,
            machines=self.instance.machines,
        )
        objective_value = calculate_objective_value(
            schedule,
            self.instance,
            self.objective,
        )
        return _GreedyResult(
            scheduled_tasks=scheduled_tasks,
            schedule=schedule,
            objective=objective_value,
        )

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
        # Locked-task changes invalidate the cached bounds / feasibility.
        self.analysis.reset_caches()

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
