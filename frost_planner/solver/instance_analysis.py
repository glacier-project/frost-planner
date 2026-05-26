# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Instance-level analysis shared by every solver.

`InstanceAnalysis` owns the per-solve lookup caches, the critical-path
forward/backward bounds, window arithmetic, symmetry detectors, and
the candidate-ordering heuristic. The CP-SAT solver uses it for model
construction; the stochastic and genetic solvers can use it to seed
their initial populations and to prune redundant permutations.
"""

import random
from dataclasses import dataclass

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.schedule import ScheduledTask


@dataclass(frozen=True)
class TimeWindow:
    """Closed-open integer time window."""

    start: int
    end: int


class InstanceAnalysis:
    """Cached instance analysis used by every solver."""

    def __init__(
        self,
        instance: SchedulingInstance,
        locked_tasks: dict[str, ScheduledTask],
        suitable_machines_map: dict[str, list[Machine]],
    ) -> None:
        self.instance = instance
        # Shared reference: callers (BaseSolver) mutate this dict via
        # lock_tasks() and the analysis sees the new state immediately.
        self.locked_tasks = locked_tasks
        self.suitable_machines_map = suitable_machines_map
        self.reset_caches()

    def reset_caches(self) -> None:
        """Clear all per-solve memoisation caches."""
        self._processing_time_cache: dict[tuple[str, str], int] = {}
        self._min_processing_cache: dict[str, int] = {}
        self._max_processing_cache: dict[str, int] = {}
        self._min_travel_cache: dict[tuple[str, str], int] = {}
        self._max_travel_cache: dict[tuple[str, str], int] = {}
        # Populated by feasible_machines_by_task; consulted by
        # possible_machines_for_task to surface the pruned set.
        self.feasible_machines_cache: dict[str, list[Machine]] | None = None
        self._machine_can_process_cache: dict[
            tuple[str, str, int | None, int | None], bool
        ] = {}
        self._relevant_unavailable_cache: dict[
            tuple[str, int, int], list[TimeWindow]
        ] = {}

    def set_feasible_machines(
        self, feasible_machines: dict[str, list[Machine]]
    ) -> None:
        """Install the pruned feasible-machine map and invalidate stale caches.

        The lookup caches (`min/max_processing_time`,
        `min/max_travel_time`) may have been populated against the
        unpruned suitable-machines view; clear them so subsequent
        lookups see the tighter pruned values.
        """
        self.feasible_machines_cache = feasible_machines
        self._min_processing_cache = {}
        self._max_processing_cache = {}
        self._min_travel_cache = {}
        self._max_travel_cache = {}

    # ----- Lookups ---------------------------------------------------

    def all_tasks(self) -> list[Task]:
        """Return all tasks in instance order."""
        return [task for job in self.instance.jobs for task in job.tasks]

    def processing_time_on(self, task: Task, machine: Machine) -> int:
        """Return the task's processing time on a machine."""
        key = (task.id, machine.id)
        cached = self._processing_time_cache.get(key)
        if cached is not None:
            return cached
        value = task.processing_time_on(machine)
        self._processing_time_cache[key] = value
        return value

    def min_processing_time(self, task: Task) -> int:
        """Return the shortest possible processing time for a task."""
        cached = self._min_processing_cache.get(task.id)
        if cached is not None:
            return cached
        machines = self.possible_machines_for_task(task)
        if not machines:
            value = task.processing_time
        else:
            value = min(
                self.processing_time_on(task, machine) for machine in machines
            )
        self._min_processing_cache[task.id] = value
        return value

    def max_processing_time(self, task: Task) -> int:
        """Return the longest possible processing time for a task."""
        cached = self._max_processing_cache.get(task.id)
        if cached is not None:
            return cached
        machines = self.possible_machines_for_task(task)
        if not machines:
            value = task.processing_time
        else:
            value = max(
                self.processing_time_on(task, machine) for machine in machines
            )
        self._max_processing_cache[task.id] = value
        return value

    def possible_machines_for_task(self, task: Task) -> list[Machine]:
        """Return machines that can process a task.

        Reads from the feasibility-pruned cache when populated (by
        `feasible_machines_by_task` + `set_feasible_machines`), so
        downstream lookups see the same pruned view as the model.
        Locked tasks always return their pinned machine.
        """
        locked_task = self.locked_tasks.get(task.id)
        if locked_task is not None:
            return [locked_task.machine]
        if self.feasible_machines_cache is not None:
            cached = self.feasible_machines_cache.get(task.id)
            if cached is not None:
                return cached
        return self.suitable_machines_map.get(task.id, [])

    def minimum_travel_time(self, dependency: Task, task: Task) -> int:
        """Return a lower bound on travel time between two tasks."""
        key = (dependency.id, task.id)
        cached = self._min_travel_cache.get(key)
        if cached is not None:
            return cached
        dependency_machines = self.possible_machines_for_task(dependency)
        current_machines = self.possible_machines_for_task(task)
        if not dependency_machines or not current_machines:
            value = 0
        else:
            value = min(
                self.instance.get_travel_time(
                    dependency_machine,
                    current_machine,
                )
                for dependency_machine in dependency_machines
                for current_machine in current_machines
            )
        self._min_travel_cache[key] = value
        return value

    def maximum_travel_time(self, dependency: Task, task: Task) -> int:
        """Return an upper bound on travel time between two tasks."""
        key = (dependency.id, task.id)
        cached = self._max_travel_cache.get(key)
        if cached is not None:
            return cached
        dependency_machines = self.possible_machines_for_task(dependency)
        current_machines = self.possible_machines_for_task(task)
        if not dependency_machines or not current_machines:
            value = 0
        else:
            value = max(
                self.instance.get_travel_time(
                    dependency_machine,
                    current_machine,
                )
                for dependency_machine in dependency_machines
                for current_machine in current_machines
            )
        self._max_travel_cache[key] = value
        return value

    # ----- Bounds ----------------------------------------------------

    def earliest_bounds(
        self, start_time: int
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Compute critical-path-style earliest start and end per task."""
        tasks = self.all_tasks()
        task_by_id = {task.id: task for task in tasks}
        earliest_start = {task.id: start_time for task in tasks}
        earliest_end: dict[str, int] = {}
        remaining = set()

        for task in tasks:
            locked_task = self.locked_tasks.get(task.id)
            if locked_task is None:
                remaining.add(task.id)
                continue
            earliest_start[task.id] = locked_task.start_time
            earliest_end[task.id] = locked_task.end_time

        while remaining:
            made_progress = False
            for task in tasks:
                if task.id not in remaining:
                    continue
                if any(
                    dependency_id not in earliest_end
                    for dependency_id in task.dependencies
                    if dependency_id in task_by_id
                ):
                    continue

                task_lower_bound = start_time
                for dependency_id in task.dependencies:
                    if dependency_id not in task_by_id:
                        raise ValueError(
                            f"Task {task.id} depends on unknown task "
                            f"{dependency_id}."
                        )
                    dependency = task_by_id[dependency_id]
                    task_lower_bound = max(
                        task_lower_bound,
                        earliest_end[dependency_id]
                        + self.minimum_travel_time(dependency, task),
                    )

                earliest_start[task.id] = task_lower_bound
                earliest_end[task.id] = (
                    task_lower_bound + self.min_processing_time(task)
                )
                remaining.remove(task.id)
                made_progress = True

            if not made_progress:
                break

        return earliest_start, earliest_end

    def latest_bounds(
        self,
        start_time: int,
        effective_horizon: int,
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Backward critical-path: latest start/end per task."""
        tasks = self.all_tasks()
        task_by_id = {task.id: task for task in tasks}
        successors_by_id: dict[str, list[str]] = {task.id: [] for task in tasks}
        for task in tasks:
            for dependency_id in task.dependencies:
                if dependency_id in task_by_id:
                    successors_by_id[dependency_id].append(task.id)

        latest_end: dict[str, int] = {
            task.id: effective_horizon for task in tasks
        }
        latest_start: dict[str, int] = {
            task.id: max(
                start_time,
                effective_horizon - self.min_processing_time(task),
            )
            for task in tasks
        }
        for scheduled_task in self.locked_tasks.values():
            task_id = scheduled_task.task.id
            if task_id not in latest_end:
                continue
            latest_end[task_id] = min(
                latest_end[task_id], scheduled_task.end_time
            )
            latest_start[task_id] = min(
                latest_start[task_id], scheduled_task.start_time
            )

        pending = {
            task.id for task in tasks if task.id not in self.locked_tasks
        }
        while pending:
            progress = False
            for task in tasks:
                if task.id not in pending:
                    continue
                successors = successors_by_id[task.id]
                if any(successor_id in pending for successor_id in successors):
                    continue
                for successor_id in successors:
                    successor = task_by_id[successor_id]
                    travel = self.minimum_travel_time(task, successor)
                    latest_end[task.id] = min(
                        latest_end[task.id],
                        latest_start[successor_id] - travel,
                    )
                latest_start[task.id] = max(
                    start_time,
                    latest_end[task.id] - self.min_processing_time(task),
                )
                pending.remove(task.id)
                progress = True
            if not progress:
                break

        return latest_start, latest_end

    def capability_bottleneck_lower_bounds(self, start_time: int) -> list[int]:
        """Per-capability and per-capability-pair workload ceilings."""
        tasks = self.all_tasks()
        capabilities: set[str] = set()
        for task in tasks:
            capabilities.update(task.requires)
        bounds: list[int] = []
        sorted_caps = sorted(capabilities)
        cap_pairs: list[tuple[str, ...]] = [(cap,) for cap in sorted_caps]
        for index, cap_a in enumerate(sorted_caps):
            for cap_b in sorted_caps[index + 1 :]:
                cap_pairs.append((cap_a, cap_b))
        for cap_subset in cap_pairs:
            cap_set = frozenset(cap_subset)
            machines_with_all = [
                machine
                for machine in self.instance.machines
                if cap_set.issubset(machine.capabilities)
            ]
            if not machines_with_all:
                continue
            mandatory_work = sum(
                self.min_processing_time(task)
                for task in tasks
                if cap_set.issubset(task.requires)
            )
            if mandatory_work <= 0:
                continue
            ceiling = -(-mandatory_work // len(machines_with_all))
            bounds.append(start_time + ceiling)
        return bounds

    def reduced_dependencies(self) -> dict[str, list[str]]:
        """Drop dependency edges implied by another chain through a sibling."""
        tasks = self.all_tasks()
        task_by_id = {task.id: task for task in tasks}
        reduced: dict[str, list[str]] = {}
        for current in tasks:
            kept: list[str] = []
            for dependency_id in current.dependencies:
                dependency = task_by_id.get(dependency_id)
                if dependency is None:
                    kept.append(dependency_id)
                    continue
                redundant = False
                max_direct = self.maximum_travel_time(dependency, current)
                for other_id in current.dependencies:
                    if other_id == dependency_id:
                        continue
                    other = task_by_id.get(other_id)
                    if other is None:
                        continue
                    if dependency_id not in other.dependencies:
                        continue
                    min_chain = (
                        self.minimum_travel_time(dependency, other)
                        + self.min_processing_time(other)
                        + self.minimum_travel_time(other, current)
                    )
                    if min_chain >= max_direct:
                        redundant = True
                        break
                if not redundant:
                    kept.append(dependency_id)
            reduced[current.id] = kept
        return reduced

    # ----- Window arithmetic -----------------------------------------

    @staticmethod
    def normalise_windows(
        intervals: list[tuple[int, int]],
        lower_bound: int,
        upper_bound: int,
    ) -> list[TimeWindow]:
        """Clip and merge machine availability windows."""
        windows: list[TimeWindow] = []
        for start, end in sorted(intervals):
            clipped_start = max(start, lower_bound)
            clipped_end = min(end, upper_bound)
            if clipped_start >= clipped_end:
                continue
            if windows and clipped_start <= windows[-1].end:
                windows[-1] = TimeWindow(
                    windows[-1].start,
                    max(windows[-1].end, clipped_end),
                )
            else:
                windows.append(TimeWindow(clipped_start, clipped_end))
        return windows

    @staticmethod
    def unavailable_windows(
        free_windows: list[TimeWindow],
        lower_bound: int,
        upper_bound: int,
    ) -> list[TimeWindow]:
        """Return the complement of free windows within the horizon."""
        unavailable: list[TimeWindow] = []
        cursor = lower_bound
        for window in free_windows:
            if cursor < window.start:
                unavailable.append(TimeWindow(cursor, window.start))
            cursor = max(cursor, window.end)
        if cursor < upper_bound:
            unavailable.append(TimeWindow(cursor, upper_bound))
        return unavailable

    def relevant_unavailable_windows(
        self,
        unavailable_windows: list[TimeWindow],
        start_lower_bound: int,
        end_upper_bound: int,
        machine_id: str | None = None,
    ) -> list[TimeWindow]:
        """Return unavailable windows that can overlap an interval."""
        if machine_id is not None:
            key = (machine_id, start_lower_bound, end_upper_bound)
            cached = self._relevant_unavailable_cache.get(key)
            if cached is not None:
                return cached
            result = [
                window
                for window in unavailable_windows
                if window.end > start_lower_bound
                and window.start < end_upper_bound
            ]
            self._relevant_unavailable_cache[key] = result
            return result
        return [
            window
            for window in unavailable_windows
            if window.end > start_lower_bound and window.start < end_upper_bound
        ]

    def machine_can_process_task(
        self,
        task: Task,
        machine: Machine,
        free_windows: list[TimeWindow],
        earliest_start: int | None = None,
        latest_end: int | None = None,
    ) -> bool:
        """Return whether a machine has enough free time for a task.

        When ``earliest_start`` / ``latest_end`` are provided, the
        feasibility check is restricted to the portion of each free
        window that intersects ``[earliest_start, latest_end]``.
        """
        cache_key = (task.id, machine.id, earliest_start, latest_end)
        cached = self._machine_can_process_cache.get(cache_key)
        if cached is not None:
            return cached
        processing_time = self.processing_time_on(task, machine)
        intersections: list[int] = []
        for window in free_windows:
            usable_start = (
                max(window.start, earliest_start)
                if earliest_start is not None
                else window.start
            )
            usable_end = (
                min(window.end, latest_end)
                if latest_end is not None
                else window.end
            )
            length = usable_end - usable_start
            if length > 0:
                intersections.append(length)
        if not intersections:
            result = False
        elif task.allow_breaks:
            result = sum(intersections) >= processing_time
        else:
            result = any(length >= processing_time for length in intersections)
        self._machine_can_process_cache[cache_key] = result
        return result

    def feasible_machines_by_task(
        self,
        tasks: list[Task],
        free_windows_by_machine: dict[str, list[TimeWindow]],
        prune_infeasible_alternatives: bool = True,
        earliest_start_by_task: dict[str, int] | None = None,
        latest_end_by_task: dict[str, int] | None = None,
    ) -> dict[str, list[Machine]]:
        """Return feasible machines after optional availability pruning."""
        feasible_machines_by_task: dict[str, list[Machine]] = {}
        for task in tasks:
            locked_task = self.locked_tasks.get(task.id)
            if locked_task is not None:
                feasible_machines_by_task[task.id] = [locked_task.machine]
                continue

            suitable_machines = self.suitable_machines_map[task.id]
            if not suitable_machines:
                raise ValueError(
                    f"No suitable machine found for task: {task.id}"
                )

            band_start = (
                earliest_start_by_task.get(task.id)
                if earliest_start_by_task is not None
                else None
            )
            band_end = (
                latest_end_by_task.get(task.id)
                if latest_end_by_task is not None
                else None
            )

            feasible_machines = []
            for machine in suitable_machines:
                free_windows = free_windows_by_machine[machine.id]
                if (
                    prune_infeasible_alternatives
                    and not self.machine_can_process_task(
                        task,
                        machine,
                        free_windows,
                        earliest_start=band_start,
                        latest_end=band_end,
                    )
                ):
                    continue
                feasible_machines.append(machine)

            if not feasible_machines:
                raise ValueError(
                    "No feasible machine alternative found for task "
                    f"{task.id} within the current availability windows."
                )
            feasible_machines_by_task[task.id] = feasible_machines

        return feasible_machines_by_task

    # ----- Symmetry detection ----------------------------------------

    def identical_job_groups(self) -> list[list[Job]]:
        """Group jobs that share an identical task-sequence signature."""
        jobs = list(self.instance.jobs)
        all_task_ids = {task.id for job in jobs for task in job.tasks}
        locked_task_ids = set(self.locked_tasks)
        signatures: dict[object, list[Job]] = {}
        for job in jobs:
            within_ids = {task.id for task in job.tasks}
            position = {task.id: idx for idx, task in enumerate(job.tasks)}
            cross_job_dep = False
            has_locked_task = False
            for task in job.tasks:
                if task.id in locked_task_ids:
                    has_locked_task = True
                    break
                for dependency_id in task.dependencies:
                    if (
                        dependency_id not in within_ids
                        and dependency_id in all_task_ids
                    ):
                        cross_job_dep = True
                        break
                if cross_job_dep:
                    break
            if cross_job_dep or has_locked_task:
                continue
            task_signatures: list[tuple[object, ...]] = []
            for task in job.tasks:
                within_dep_positions = tuple(
                    sorted(
                        position[dependency_id]
                        for dependency_id in task.dependencies
                        if dependency_id in within_ids
                    )
                )
                task_signatures.append(
                    (
                        tuple(sorted(task.requires)),
                        task.processing_time,
                        tuple(sorted(task.machine_processing_times.items())),
                        task.allow_breaks,
                        within_dep_positions,
                    )
                )
            job_sig = (job.due_date, tuple(task_signatures))
            signatures.setdefault(job_sig, []).append(job)
        return [
            sorted(group, key=lambda job: job.id)
            for group in signatures.values()
            if len(group) >= 2
        ]

    def identical_machine_groups(
        self,
        free_windows_by_machine: dict[str, list[TimeWindow]],
    ) -> list[list[Machine]]:
        """Group machines that are mutually interchangeable for scheduling."""
        tasks = self.all_tasks()
        machines = self.instance.machines
        sorted_other_ids: dict[str, list[str]] = {
            machine.id: sorted(
                other.id for other in machines if other.id != machine.id
            )
            for machine in machines
        }
        signatures: dict[tuple[object, ...], list[Machine]] = {}
        for machine in machines:
            cap = tuple(sorted(machine.capabilities))
            windows = tuple(free_windows_by_machine[machine.id])
            processing_signature = tuple(
                (task.id, self.processing_time_on(task, machine))
                for task in tasks
                if machine in self.suitable_machines_map.get(task.id, [])
            )
            travel_out = tuple(
                (
                    other_id,
                    self.instance.travel_times[machine.id].get(other_id),
                )
                for other_id in sorted_other_ids[machine.id]
                if machine.id in self.instance.travel_times
            )
            travel_in = tuple(
                (
                    other_id,
                    self.instance.travel_times.get(other_id, {}).get(
                        machine.id
                    ),
                )
                for other_id in sorted_other_ids[machine.id]
            )
            signatures.setdefault(
                (cap, windows, processing_signature, travel_out, travel_in),
                [],
            ).append(machine)
        groups: list[list[Machine]] = []
        for group in signatures.values():
            if len(group) < 2:
                continue
            zero_within_group = True
            for index_a, machine_a in enumerate(group):
                for machine_b in group[index_a + 1 :]:
                    try:
                        forward = self.instance.get_travel_time(
                            machine_a, machine_b
                        )
                        backward = self.instance.get_travel_time(
                            machine_b, machine_a
                        )
                    except ValueError:
                        zero_within_group = False
                        break
                    if forward != 0 or backward != 0:
                        zero_within_group = False
                        break
                if not zero_within_group:
                    break
            if zero_within_group:
                groups.append(sorted(group, key=lambda m: m.id))
        return groups

    # ----- Heuristic ordering ----------------------------------------

    def job_workload(self, job: Job) -> int:
        """Sum of shortest-machine processing times across a job's tasks."""
        return sum(self.min_processing_time(task) for task in job.tasks)

    def candidate_job_orderings(
        self,
        random_seeds: tuple[int, ...] = (42, 1337, 271),
    ) -> list[list[Job]]:
        """Return candidate job orderings for the heuristic incumbent.

        Useful as seeds for the stochastic / genetic solvers' initial
        populations instead of pure-random shuffles.
        """
        jobs = list(self.instance.jobs)
        far_future = (
            max(
                (job.due_date for job in jobs if job.due_date is not None),
                default=0,
            )
            + sum(self.job_workload(job) for job in jobs)
            + 1
        )
        candidates: list[list[Job]] = [list(jobs)]
        candidates.append(sorted(jobs, key=self.job_workload))
        candidates.append(sorted(jobs, key=lambda job: -self.job_workload(job)))
        candidates.append(
            sorted(
                jobs,
                key=lambda job: (
                    job.due_date if job.due_date is not None else far_future
                ),
            )
        )
        candidates.append(
            sorted(
                jobs,
                key=lambda job: (
                    (job.due_date if job.due_date is not None else far_future)
                    - self.job_workload(job)
                ),
            )
        )
        for seed in random_seeds:
            rng = random.Random(seed)
            shuffled = list(jobs)
            rng.shuffle(shuffled)
            candidates.append(shuffled)
        return candidates
