# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, override

from frost_planner.core.base import Machine, SchedulingInstance, Task
from frost_planner.core.objective import ObjectiveWeights
from frost_planner.core.schedule import ScheduledTask
from frost_planner.core.validate import validate_schedule
from frost_planner.solver import _create_schedule, _schedule_by_order
from frost_planner.solver.base_solver import BaseSolver


@dataclass(frozen=True)
class _TimeWindow:
    """Closed-open integer time window."""

    start: int
    end: int


@dataclass
class _AlternativeVariables:
    """Variables for one task-machine assignment alternative.

    `presence` is None when the alternative is the only feasible option
    and is modeled as a mandatory interval instead of an optional one.
    """

    machine: Machine
    processing_time: int
    presence: Any | None
    interval: Any
    break_time: Any


@dataclass
class _TaskVariables:
    """Variables for one task in the CP-SAT model."""

    task: Task
    start: Any
    end: Any
    machine: Any | None
    alternatives: dict[str, _AlternativeVariables]
    locked_machine: Machine | None = None


def _load_cp_model() -> Any:
    """Load OR-Tools lazily so default installs do not require it."""
    try:
        from ortools.sat.python import cp_model
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "CpSatSolver requires the ortools dependency group. Install it "
            "with `uv sync --group ortools`."
        ) from exc
    return cp_model


def _safe_name(value: str) -> str:
    """Return a CP-SAT variable-name-safe version of a user identifier."""
    return "".join(char if char.isalnum() else "_" for char in value)


class CpSatSolver(BaseSolver):
    """CP-SAT solver for Frost Planner scheduling instances."""

    def __init__(
        self,
        instance: SchedulingInstance,
        horizon: int = sys.maxsize,
        machine_intervals: dict[str, list[tuple[int, int]]] | None = None,
        time_limit_seconds: float | None = None,
        num_workers: int | None = 16,
        relative_gap: float = 0.0,
        log_search_progress: bool = False,
        use_travel_table: bool | None = None,
        travel_model: str | None = None,
        hybrid_travel_threshold: int = 16,
        use_dependency_bounds: bool = False,
        use_machine_load_bounds: bool = False,
        prune_infeasible_alternatives: bool = True,
        use_heuristic_hints: bool = True,
        objective: ObjectiveWeights | None = None,
    ) -> None:
        super().__init__(instance, horizon, machine_intervals, objective)
        if num_workers is not None and num_workers < 1:
            raise ValueError("num_workers must be positive.")
        if relative_gap < 0:
            raise ValueError("relative_gap must be non-negative.")
        if hybrid_travel_threshold < 1:
            raise ValueError("hybrid_travel_threshold must be positive.")
        if travel_model is None:
            travel_model = "table" if use_travel_table is True else "pairwise"
        if travel_model not in {"table", "pairwise", "hybrid"}:
            raise ValueError(
                "travel_model must be 'table', 'pairwise', or 'hybrid'."
            )

        self.time_limit_seconds = time_limit_seconds
        self.num_workers = num_workers
        self.relative_gap = relative_gap
        self.log_search_progress = log_search_progress
        self.travel_model = travel_model
        self.use_travel_table = travel_model == "table"
        self.hybrid_travel_threshold = hybrid_travel_threshold
        self.use_dependency_bounds = use_dependency_bounds
        self.use_machine_load_bounds = use_machine_load_bounds
        self.prune_infeasible_alternatives = prune_infeasible_alternatives
        self.use_heuristic_hints = use_heuristic_hints
        self.last_status: str | None = None
        self.last_objective_value: float | None = None
        self.last_best_bound: float | None = None
        self.last_wall_time_seconds: float | None = None

    def _all_tasks(self) -> list[Task]:
        """Return all tasks in instance order."""
        return [task for job in self.instance.jobs for task in job.tasks]

    def _processing_time_on(self, task: Task, machine: Machine) -> int:
        """Return the task processing time on a machine."""
        return task.processing_time_on(machine)

    def _min_processing_time(self, task: Task) -> int:
        """Return the shortest possible processing time for a task."""
        machines = self._possible_machines_for_task(task)
        if not machines:
            return task.processing_time
        return min(
            self._processing_time_on(task, machine) for machine in machines
        )

    def _max_processing_time(self, task: Task) -> int:
        """Return the longest possible processing time for a task."""
        machines = self._possible_machines_for_task(task)
        if not machines:
            return task.processing_time
        return max(
            self._processing_time_on(task, machine) for machine in machines
        )

    def _possible_machines_for_task(self, task: Task) -> list[Machine]:
        """Return machines that can process a task in the CP-SAT model."""
        locked_task = self.locked_tasks.get(task.id)
        if locked_task is not None:
            return [locked_task.machine]
        return self.suitable_machines_map.get(task.id, [])

    def _minimum_travel_time(self, dependency: Task, task: Task) -> int:
        """Return a lower bound on travel time between two tasks."""
        dependency_machines = self._possible_machines_for_task(dependency)
        current_machines = self._possible_machines_for_task(task)
        if not dependency_machines or not current_machines:
            return 0
        return min(
            self.instance.get_travel_time(
                dependency_machine,
                current_machine,
            )
            for dependency_machine in dependency_machines
            for current_machine in current_machines
        )

    def _earliest_start_bounds(self, start_time: int) -> dict[str, int]:
        """Compute conservative dependency-based task start lower bounds."""
        tasks = self._all_tasks()
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
                        + self._minimum_travel_time(dependency, task),
                    )

                earliest_start[task.id] = task_lower_bound
                earliest_end[task.id] = (
                    task_lower_bound + self._min_processing_time(task)
                )
                remaining.remove(task.id)
                made_progress = True

            if not made_progress:
                break

        return earliest_start

    def _effective_horizon(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int,
    ) -> int:
        """Compute a finite CP-SAT horizon."""
        if self.horizon != sys.maxsize:
            return self.horizon

        finite_ends = [
            end
            for intervals in machine_intervals.values()
            for _, end in intervals
            if end != sys.maxsize
        ]
        all_machines_have_finite_end = all(
            any(
                end != sys.maxsize
                for _, end in machine_intervals.get(m.id, [])
            )
            for m in self.instance.machines
        )
        if finite_ends and all_machines_have_finite_end:
            return max(max(finite_ends), start_time)

        processing_time = sum(
            self._max_processing_time(task) for task in self._all_tasks()
        )
        max_locked_end = max(
            (st.end_time for st in self.locked_tasks.values()),
            default=start_time,
        )
        travel_slack = 0
        for task in self._all_tasks():
            for _ in task.dependencies:
                travel_slack += max(
                    (
                        travel_time
                        for destinations in self.instance.travel_times.values()
                        for travel_time in destinations.values()
                    ),
                    default=0,
                )

        task_slack = len(self._all_tasks())
        return (
            max(start_time, max_locked_end)
            + processing_time
            + travel_slack
            + task_slack
        )

    def _normalise_windows(
        self,
        intervals: list[tuple[int, int]],
        lower_bound: int,
        upper_bound: int,
    ) -> list[_TimeWindow]:
        """Clip and merge machine availability windows."""
        windows: list[_TimeWindow] = []
        for start, end in sorted(intervals):
            clipped_start = max(start, lower_bound)
            clipped_end = min(end, upper_bound)
            if clipped_start >= clipped_end:
                continue
            if windows and clipped_start <= windows[-1].end:
                windows[-1] = _TimeWindow(
                    windows[-1].start,
                    max(windows[-1].end, clipped_end),
                )
            else:
                windows.append(_TimeWindow(clipped_start, clipped_end))
        return windows

    def _unavailable_windows(
        self,
        free_windows: list[_TimeWindow],
        lower_bound: int,
        upper_bound: int,
    ) -> list[_TimeWindow]:
        """Return the complement of free windows within the horizon."""
        unavailable: list[_TimeWindow] = []
        cursor = lower_bound
        for window in free_windows:
            if cursor < window.start:
                unavailable.append(_TimeWindow(cursor, window.start))
            cursor = max(cursor, window.end)
        if cursor < upper_bound:
            unavailable.append(_TimeWindow(cursor, upper_bound))
        return unavailable

    def _relevant_unavailable_windows(
        self,
        unavailable_windows: list[_TimeWindow],
        start_lower_bound: int,
        end_upper_bound: int,
    ) -> list[_TimeWindow]:
        """Return unavailable windows that can overlap an interval."""
        return [
            window
            for window in unavailable_windows
            if window.end > start_lower_bound and window.start < end_upper_bound
        ]

    def _machine_can_process_task(
        self,
        task: Task,
        machine: Machine,
        free_windows: list[_TimeWindow],
    ) -> bool:
        """Return whether a machine has enough free time for a task."""
        processing_time = self._processing_time_on(task, machine)
        if task.allow_breaks:
            total_available_time = sum(
                window.end - window.start for window in free_windows
            )
            return total_available_time >= processing_time

        return any(
            window.end - window.start >= processing_time
            for window in free_windows
        )

    def _feasible_machines_by_task(
        self,
        tasks: list[Task],
        free_windows_by_machine: dict[str, list[_TimeWindow]],
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

            feasible_machines = []
            for machine in suitable_machines:
                free_windows = free_windows_by_machine[machine.id]
                if (
                    self.prune_infeasible_alternatives
                    and not self._machine_can_process_task(
                        task,
                        machine,
                        free_windows,
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

    def _table_machine_task_ids(
        self,
        tasks: list[Task],
        feasible_machines_by_task: dict[str, list[Machine]],
    ) -> set[str]:
        """Return tasks that need machine-index variables for table edges."""
        if self.travel_model not in {"table", "hybrid"}:
            return set()

        task_by_id = {task.id: task for task in tasks}
        task_ids: set[str] = set()
        for task in tasks:
            current_machines = feasible_machines_by_task[task.id]
            for dependency_id in task.dependencies:
                if dependency_id not in task_by_id:
                    raise ValueError(
                        f"Task {task.id} depends on unknown task "
                        f"{dependency_id}."
                    )
                dependency_machines = feasible_machines_by_task[dependency_id]
                travel_times = [
                    self.instance.get_travel_time(
                        dependency_machine,
                        current_machine,
                    )
                    for dependency_machine in dependency_machines
                    for current_machine in current_machines
                ]
                if min(travel_times) == max(travel_times):
                    continue

                use_table = self.travel_model == "table"
                if self.travel_model == "hybrid":
                    use_table = (
                        len(dependency_machines) * len(current_machines)
                        > self.hybrid_travel_threshold
                    )
                if use_table:
                    task_ids.add(dependency_id)
                    task_ids.add(task.id)

        return task_ids

    def _bind_non_breakable_start_to_window(
        self,
        model: Any,
        cp_model: Any,
        value: Any,
        presence: Any | None,
        free_windows: list[_TimeWindow],
        processing_time: int,
        *,
        lower_bound: int,
        upper_bound: int,
    ) -> None:
        """Restrict a non-breakable start so the duration fits in a window."""
        domain_intervals = []
        for window in free_windows:
            if window.end - window.start < processing_time:
                continue
            domain_start = max(window.start, lower_bound)
            domain_end = min(window.end - processing_time, upper_bound)
            if domain_start <= domain_end:
                domain_intervals.append((domain_start, domain_end))
        if not domain_intervals:
            if presence is None:
                raise ValueError(
                    "Mandatory non-breakable alternative cannot fit within "
                    "available windows during model build."
                )
            model.Add(presence == 0)
            return
        constraint = model.AddLinearExpressionInDomain(
            value,
            cp_model.Domain.FromIntervals(domain_intervals),
        )
        if presence is not None:
            constraint.OnlyEnforceIf(presence)

    def _bind_point_to_free_window(
        self,
        model: Any,
        cp_model: Any,
        value: Any,
        presence: Any | None,
        free_windows: list[_TimeWindow],
        *,
        is_start: bool,
        lower_bound: int,
        upper_bound: int,
    ) -> None:
        """Force a present start or end point to lie on available time."""
        domain_intervals = []
        if is_start:
            for window in free_windows:
                domain_start = max(window.start, lower_bound)
                domain_end = min(window.end - 1, upper_bound)
                if domain_start <= domain_end:
                    domain_intervals.append((domain_start, domain_end))
        else:
            for window in free_windows:
                domain_start = max(window.start, lower_bound)
                domain_end = min(window.end, upper_bound)
                if domain_start <= domain_end:
                    domain_intervals.append((domain_start, domain_end))
        if not domain_intervals:
            if presence is None:
                raise ValueError(
                    "Mandatory alternative cannot fit within available "
                    "windows during model build."
                )
            model.Add(presence == 0)
            return

        constraint = model.AddLinearExpressionInDomain(
            value,
            cp_model.Domain.FromIntervals(domain_intervals),
        )
        if presence is not None:
            constraint.OnlyEnforceIf(presence)

    def _create_break_time_var(
        self,
        model: Any,
        start: Any,
        end: Any,
        unavailable_windows: list[_TimeWindow],
        horizon: int,
        name: str,
        start_lower_bound: int,
        end_upper_bound: int,
    ) -> Any:
        """Create a variable for unavailable time inside an interval."""
        unavailable_windows = self._relevant_unavailable_windows(
            unavailable_windows,
            start_lower_bound,
            end_upper_bound,
        )
        max_break_time = sum(
            window.end - window.start for window in unavailable_windows
        )
        break_time = model.NewIntVar(0, max_break_time, f"{name}_break_time")
        if not unavailable_windows:
            model.Add(break_time == 0)
            return break_time

        zero = model.NewConstant(0)
        overlaps = []
        for idx, window in enumerate(unavailable_windows):
            min_end = model.NewIntVar(0, horizon, f"{name}_min_end_{idx}")
            max_start = model.NewIntVar(0, horizon, f"{name}_max_start_{idx}")
            difference = model.NewIntVar(
                -horizon,
                horizon,
                f"{name}_diff_{idx}",
            )
            overlap = model.NewIntVar(
                0,
                window.end - window.start,
                f"{name}_overlap_{idx}",
            )
            model.AddMinEquality(
                min_end,
                [end, model.NewConstant(window.end)],
            )
            model.AddMaxEquality(
                max_start,
                [start, model.NewConstant(window.start)],
            )
            model.Add(difference == min_end - max_start)
            model.AddMaxEquality(overlap, [difference, zero])
            overlaps.append(overlap)

        model.Add(break_time == sum(overlaps))
        return break_time

    def _create_locked_variables(
        self,
        model: Any,
        no_overlap_intervals: dict[str, list[Any]],
        machine_indices: dict[str, int] | None,
        task_ids_requiring_machine_variables: set[str],
        start_time: int,
    ) -> dict[str, _TaskVariables]:
        """Create fixed variables and intervals for locked tasks."""
        locked_variables: dict[str, _TaskVariables] = {}
        for scheduled_task in self.locked_tasks.values():
            task_id = scheduled_task.task.id
            if task_id not in self.task_id_map:
                continue
            if scheduled_task.machine.id not in self.machine_id_map:
                raise ValueError(
                    f"Locked task {task_id} is assigned to unknown machine "
                    f"{scheduled_task.machine.id}."
                )

            start = model.NewConstant(scheduled_task.start_time)
            end = model.NewConstant(scheduled_task.end_time)
            locked_variables[task_id] = _TaskVariables(
                task=scheduled_task.task,
                start=start,
                end=end,
                machine=(
                    model.NewConstant(machine_indices[scheduled_task.machine.id])
                    if machine_indices is not None
                    and task_id in task_ids_requiring_machine_variables
                    else None
                ),
                alternatives={},
                locked_machine=scheduled_task.machine,
            )

            if scheduled_task.end_time <= start_time:
                continue

            elapsed_duration = (
                scheduled_task.end_time - scheduled_task.start_time
            )
            interval = model.NewIntervalVar(
                start,
                elapsed_duration,
                end,
                f"locked_{_safe_name(task_id)}",
            )
            no_overlap_intervals[scheduled_task.machine.id].append(interval)
        return locked_variables

    def _create_fixed_unavailable_intervals(
        self,
        model: Any,
        unavailable_windows_by_machine: dict[str, list[_TimeWindow]],
    ) -> dict[str, list[Any]]:
        """Create fixed intervals for machine unavailable periods."""
        unavailable_intervals: dict[str, list[Any]] = {
            machine.id: [] for machine in self.instance.machines
        }
        for machine in self.instance.machines:
            for idx, window in enumerate(
                unavailable_windows_by_machine[machine.id]
            ):
                unavailable_intervals[machine.id].append(
                    model.NewIntervalVar(
                        model.NewConstant(window.start),
                        window.end - window.start,
                        model.NewConstant(window.end),
                        f"unavailable_{_safe_name(machine.id)}_{idx}",
                    )
                )
        return unavailable_intervals

    def _create_heuristic_hint(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        effective_horizon: int,
        start_time: int,
    ) -> dict[str, ScheduledTask] | None:
        """Create a greedy feasible schedule to warm-start CP-SAT."""
        locked_tasks_map = {
            scheduled_task.task.id: scheduled_task
            for scheduled_task in self.locked_tasks.values()
        }
        try:
            scheduled_tasks = _schedule_by_order(
                self.instance,
                self.instance.jobs,
                self.instance.machines,
                deepcopy(machine_intervals),
                effective_horizon,
                self.instance.travel_times,
                self.machine_id_map,
                self.suitable_machines_map,
                initial_scheduled_tasks=locked_tasks_map,
                min_time=start_time,
            )
            schedule = _create_schedule(
                scheduled_tasks=scheduled_tasks,
                machines=self.instance.machines,
            )
            if not validate_schedule(schedule, self.instance):
                return None
        except (KeyError, ValueError):
            return None

        return {
            scheduled_task.task.id: scheduled_task
            for scheduled_task in scheduled_tasks
        }

    def _add_heuristic_hint(
        self,
        model: Any,
        makespan: Any,
        task_variables: dict[str, _TaskVariables],
        heuristic_hint: dict[str, ScheduledTask],
        machine_indices: dict[str, int] | None,
    ) -> None:
        """Add a greedy incumbent as CP-SAT hints."""
        hinted_tasks = [
            scheduled_task
            for task_id, scheduled_task in heuristic_hint.items()
            if task_id in task_variables
        ]
        if not hinted_tasks:
            return

        heuristic_makespan = max(
            scheduled_task.end_time for scheduled_task in hinted_tasks
        )
        if self.objective.is_pure_makespan:
            model.Add(makespan <= heuristic_makespan)
        model.AddHint(makespan, heuristic_makespan)

        for task_id, scheduled_task in heuristic_hint.items():
            if task_id not in task_variables:
                continue
            variables = task_variables[task_id]
            if variables.locked_machine is not None:
                continue

            model.AddHint(variables.start, scheduled_task.start_time)
            model.AddHint(variables.end, scheduled_task.end_time)

            if (
                variables.machine is not None
                and machine_indices is not None
                and scheduled_task.machine.id in machine_indices
            ):
                model.AddHint(
                    variables.machine,
                    machine_indices[scheduled_task.machine.id],
                )

            for machine_id, alternative in variables.alternatives.items():
                if alternative.presence is None:
                    continue
                model.AddHint(
                    alternative.presence,
                    int(machine_id == scheduled_task.machine.id),
                )

    def _job_completion_variables(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        horizon: int,
    ) -> dict[str, Any]:
        """Create job completion variables from task end variables."""
        job_completion_vars = {}
        for job in self.instance.jobs:
            job_task_ends = [
                task_variables[task.id].end
                for task in job.tasks
                if task.id in task_variables
            ]
            if not job_task_ends:
                job_completion_vars[job.id] = model.NewConstant(0)
                continue

            job_completion = model.NewIntVar(
                0,
                horizon,
                f"job_end_{_safe_name(job.id)}",
            )
            model.AddMaxEquality(job_completion, job_task_ends)
            job_completion_vars[job.id] = job_completion
        return job_completion_vars

    def _objective_expression(
        self,
        model: Any,
        makespan: Any,
        job_completion_vars: dict[str, Any],
        horizon: int,
    ) -> Any:
        """Build the configured CP-SAT objective expression."""
        terms = []
        objective = self.objective
        if objective.makespan:
            terms.append(objective.makespan * makespan)
        if objective.total_flow_time:
            terms.extend(
                objective.total_flow_time * job_completion
                for job_completion in job_completion_vars.values()
            )

        needs_per_job_term = bool(
            objective.num_tardy_jobs
            or objective.total_tardiness
            or objective.total_earliness
            or objective.max_tardiness
        )
        tardiness_vars: list[Any] = []
        if needs_per_job_term:
            for job in self.instance.jobs:
                if job.due_date is None:
                    continue

                job_name = _safe_name(job.id)
                completion = job_completion_vars[job.id]

                if objective.total_tardiness or objective.max_tardiness:
                    lateness = model.NewIntVar(
                        -job.due_date,
                        horizon,
                        f"lateness_{job_name}",
                    )
                    model.Add(lateness == completion - job.due_date)
                    tardiness = model.NewIntVar(
                        0,
                        horizon,
                        f"tardiness_{job_name}",
                    )
                    model.AddMaxEquality(
                        tardiness,
                        [lateness, model.NewConstant(0)],
                    )
                    tardiness_vars.append(tardiness)
                    if objective.total_tardiness:
                        terms.append(objective.total_tardiness * tardiness)

                if objective.num_tardy_jobs:
                    tardy = model.NewBoolVar(f"tardy_{job_name}")
                    model.Add(completion >= job.due_date + 1).OnlyEnforceIf(
                        tardy
                    )
                    model.Add(completion <= job.due_date).OnlyEnforceIf(
                        tardy.Not()
                    )
                    terms.append(objective.num_tardy_jobs * tardy)
                if objective.total_earliness:
                    earliness_delta = model.NewIntVar(
                        -horizon,
                        job.due_date,
                        f"earliness_delta_{job_name}",
                    )
                    model.Add(earliness_delta == job.due_date - completion)
                    earliness = model.NewIntVar(
                        0,
                        job.due_date,
                        f"earliness_{job_name}",
                    )
                    model.AddMaxEquality(
                        earliness,
                        [earliness_delta, model.NewConstant(0)],
                    )
                    terms.append(objective.total_earliness * earliness)

        if objective.max_tardiness:
            max_tardiness = model.NewIntVar(0, horizon, "max_tardiness")
            if tardiness_vars:
                model.AddMaxEquality(max_tardiness, tardiness_vars)
            else:
                model.Add(max_tardiness == 0)
            terms.append(objective.max_tardiness * max_tardiness)

        return sum(terms)

    def _machine_choices(
        self,
        task_variables: _TaskVariables,
    ) -> list[tuple[Machine, Any | None]]:
        """Return possible selected machines and their enforcement literals."""
        if task_variables.locked_machine is not None:
            return [(task_variables.locked_machine, None)]
        return [
            (alternative.machine, alternative.presence)
            for alternative in task_variables.alternatives.values()
        ]

    def _add_direct_dependency_constraint(
        self,
        model: Any,
        dependency_variables: _TaskVariables,
        current_variables: _TaskVariables,
        travel_time: int,
    ) -> None:
        """Add an unconditional dependency with a fixed travel time."""
        model.Add(
            current_variables.start >= dependency_variables.end + travel_time
        )

    def _dependency_travel_options(
        self,
        dependency_choices: list[tuple[Machine, Any | None]],
        current_choices: list[tuple[Machine, Any | None]],
    ) -> list[tuple[Machine, Any | None, Machine, Any | None, int]]:
        """Return all possible dependency machine-pair travel options."""
        return [
            (
                dependency_machine,
                dependency_presence,
                current_machine,
                current_presence,
                self.instance.get_travel_time(
                    dependency_machine,
                    current_machine,
                ),
            )
            for dependency_machine, dependency_presence in dependency_choices
            for current_machine, current_presence in current_choices
        ]

    def _add_pairwise_dependency_edge(
        self,
        model: Any,
        dependency_variables: _TaskVariables,
        current_variables: _TaskVariables,
        travel_options: list[
            tuple[Machine, Any | None, Machine, Any | None, int]
        ],
        min_travel_time: int,
    ) -> None:
        """Add pairwise reified constraints for one dependency edge."""
        self._add_direct_dependency_constraint(
            model,
            dependency_variables,
            current_variables,
            min_travel_time,
        )
        for (
            _dependency_machine,
            dependency_presence,
            _current_machine,
            current_presence,
            travel_time,
        ) in travel_options:
            if travel_time == min_travel_time:
                continue
            constraint = model.Add(
                current_variables.start
                >= dependency_variables.end + travel_time
            )
            enforcement_literals = [
                literal
                for literal in (
                    dependency_presence,
                    current_presence,
                )
                if literal is not None
            ]
            if enforcement_literals:
                constraint.OnlyEnforceIf(enforcement_literals)

    def _add_table_dependency_edge(
        self,
        model: Any,
        dependency_variables: _TaskVariables,
        current_variables: _TaskVariables,
        dependency_id: str,
        task_id: str,
        travel_options: list[
            tuple[Machine, Any | None, Machine, Any | None, int]
        ],
        min_travel_time: int,
        max_travel_time: int,
        machine_indices: dict[str, int],
    ) -> None:
        """Add a table-based travel constraint for one dependency edge."""
        travel_tuples = set()
        for (
            dependency_machine,
            _dependency_presence,
            current_machine,
            _current_presence,
            travel_time,
        ) in travel_options:
            travel_tuples.add(
                (
                    machine_indices[dependency_machine.id],
                    machine_indices[current_machine.id],
                    travel_time,
                )
            )

        travel_var = model.NewIntVar(
            min_travel_time,
            max_travel_time,
            f"travel_{_safe_name(dependency_id)}_{_safe_name(task_id)}",
        )
        if (
            dependency_variables.machine is None
            or current_variables.machine is None
        ):
            raise ValueError(
                "Table-based travel constraints require machine variables."
            )
        model.AddAllowedAssignments(
            [
                dependency_variables.machine,
                current_variables.machine,
                travel_var,
            ],
            sorted(travel_tuples),
        )
        model.Add(
            current_variables.start >= dependency_variables.end + travel_var
        )

    def _add_dependency_constraints(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        machine_indices: dict[str, int] | None,
    ) -> None:
        """Add dependencies with the configured travel formulation."""
        for task in self._all_tasks():
            current_variables = task_variables[task.id]
            for dependency_id in task.dependencies:
                if dependency_id not in task_variables:
                    raise ValueError(
                        f"Task {task.id} depends on unknown task "
                        f"{dependency_id}."
                    )

                dependency_variables = task_variables[dependency_id]
                dependency_choices = self._machine_choices(
                    dependency_variables
                )
                current_choices = self._machine_choices(current_variables)
                travel_options = self._dependency_travel_options(
                    dependency_choices,
                    current_choices,
                )
                travel_times = [
                    travel_time
                    for *_machines_and_literals, travel_time in travel_options
                ]
                min_travel_time = min(travel_times)
                max_travel_time = max(travel_times)

                if min_travel_time == max_travel_time:
                    self._add_direct_dependency_constraint(
                        model,
                        dependency_variables,
                        current_variables,
                        min_travel_time,
                    )
                    continue

                use_table = self.travel_model == "table"
                if self.travel_model == "hybrid":
                    use_table = (
                        len(dependency_choices) * len(current_choices)
                        > self.hybrid_travel_threshold
                    )

                if use_table:
                    if machine_indices is None:
                        raise ValueError(
                            "Missing machine indices for table travel model."
                        )
                    self._add_table_dependency_edge(
                        model,
                        dependency_variables,
                        current_variables,
                        dependency_id,
                        task.id,
                        travel_options,
                        min_travel_time,
                        max_travel_time,
                        machine_indices,
                    )
                else:
                    self._add_pairwise_dependency_edge(
                        model,
                        dependency_variables,
                        current_variables,
                        travel_options,
                        min_travel_time,
                    )

    def _set_num_workers(self, solver: Any) -> None:
        """Set worker count across OR-Tools parameter naming variants."""
        if self.num_workers is None:
            return
        if hasattr(solver.parameters, "num_workers"):
            solver.parameters.num_workers = self.num_workers
        else:
            solver.parameters.num_search_workers = self.num_workers

    def _configure_solver(self, solver: Any) -> None:
        """Apply user-provided CP-SAT search parameters."""
        if self.time_limit_seconds is not None:
            solver.parameters.max_time_in_seconds = self.time_limit_seconds
        self._set_num_workers(solver)
        solver.parameters.relative_gap_limit = self.relative_gap
        solver.parameters.log_search_progress = self.log_search_progress

    @override
    def _allocate_tasks(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> list[ScheduledTask]:
        cp_model = _load_cp_model()
        model = cp_model.CpModel()
        effective_horizon = self._effective_horizon(
            machine_intervals,
            start_time,
        )
        if effective_horizon < start_time:
            raise ValueError(
                f"Horizon {effective_horizon} is before start_time "
                f"{start_time}."
            )

        tasks = self._all_tasks()
        if not tasks:
            return []

        heuristic_hint = (
            self._create_heuristic_hint(
                machine_intervals,
                effective_horizon,
                start_time,
            )
            if self.use_heuristic_hints
            else None
        )
        if heuristic_hint is not None and self.objective.is_pure_makespan:
            heuristic_makespan = max(
                scheduled_task.end_time
                for scheduled_task in heuristic_hint.values()
            )
            effective_horizon = max(
                start_time,
                min(effective_horizon, heuristic_makespan),
            )

        earliest_start_bounds = (
            self._earliest_start_bounds(start_time)
            if self.use_dependency_bounds
            else {task.id: start_time for task in tasks}
        )
        machine_indices = (
            {
                machine.id: index
                for index, machine in enumerate(self.instance.machines)
            }
            if self.travel_model in {"table", "hybrid"}
            else None
        )
        free_windows_by_machine = {
            machine.id: self._normalise_windows(
                machine_intervals.get(machine.id, []),
                start_time,
                effective_horizon,
            )
            for machine in self.instance.machines
        }
        unavailable_windows_by_machine = {
            machine.id: self._unavailable_windows(
                free_windows_by_machine[machine.id],
                start_time,
                effective_horizon,
            )
            for machine in self.instance.machines
        }
        feasible_machines_by_task: dict[str, list[Machine]] | None = None
        task_ids_requiring_machine_variables: set[str] = set()
        if machine_indices is not None:
            feasible_machines_by_task = self._feasible_machines_by_task(
                tasks,
                free_windows_by_machine,
            )
            if self.travel_model == "hybrid":
                task_ids_requiring_machine_variables = {
                    task.id for task in tasks
                }
            else:
                task_ids_requiring_machine_variables = (
                    self._table_machine_task_ids(
                        tasks,
                        feasible_machines_by_task,
                    )
                )
        no_overlap_intervals: dict[str, list[Any]] = {
            machine.id: [] for machine in self.instance.machines
        }
        machines_with_future_locked_tasks = {
            scheduled_task.machine.id
            for scheduled_task in self.locked_tasks.values()
            if scheduled_task.task.id in self.task_id_map
            and scheduled_task.end_time > start_time
        }
        machines_with_breakable_alternatives: set[str] = set()
        for task in tasks:
            if task.id in self.locked_tasks or not task.allow_breaks:
                continue
            if feasible_machines_by_task is not None:
                feasible_machines = feasible_machines_by_task[task.id]
            else:
                feasible_machines = []
                for machine in self.suitable_machines_map[task.id]:
                    if (
                        not self.prune_infeasible_alternatives
                        or self._machine_can_process_task(
                            task,
                            machine,
                            free_windows_by_machine[machine.id],
                        )
                    ):
                        feasible_machines.append(machine)
            for machine in feasible_machines:
                machines_with_breakable_alternatives.add(machine.id)
        machines_requiring_separate_availability = (
            machines_with_future_locked_tasks
            | machines_with_breakable_alternatives
        )
        machine_load_terms: dict[str, list[Any]] | None = None
        if self.use_machine_load_bounds:
            machine_load_terms = {
                machine.id: [] for machine in self.instance.machines
            }
            for scheduled_task in self.locked_tasks.values():
                if scheduled_task.task.id not in self.task_id_map:
                    continue
                if scheduled_task.machine.id not in machine_load_terms:
                    raise ValueError(
                        f"Locked task {scheduled_task.task.id} is assigned "
                        f"to unknown machine {scheduled_task.machine.id}."
                    )
                if scheduled_task.end_time <= start_time:
                    continue
                locked_duration = (
                    scheduled_task.end_time
                    - max(start_time, scheduled_task.start_time)
                )
                machine_load_terms[scheduled_task.machine.id].append(
                    locked_duration
                )
        fixed_unavailable_intervals = self._create_fixed_unavailable_intervals(
            model,
            unavailable_windows_by_machine,
        )
        non_breakable_availability_intervals: dict[str, list[Any]] = {
            machine.id: [] for machine in self.instance.machines
        }
        for machine in self.instance.machines:
            if machine.id in machines_requiring_separate_availability:
                non_breakable_availability_intervals[machine.id].extend(
                    fixed_unavailable_intervals[machine.id]
                )
            else:
                no_overlap_intervals[machine.id].extend(
                    fixed_unavailable_intervals[machine.id]
                )
        task_variables = self._create_locked_variables(
            model,
            no_overlap_intervals,
            machine_indices,
            task_ids_requiring_machine_variables,
            start_time,
        )

        for task in tasks:
            if task.id in task_variables:
                continue

            task_name = _safe_name(task.id)
            min_processing_time = self._min_processing_time(task)
            task_start_lower_bound = min(
                max(start_time, earliest_start_bounds[task.id]),
                effective_horizon,
            )
            task_start_upper_bound = max(
                task_start_lower_bound,
                effective_horizon - min_processing_time,
            )
            task_end_lower_bound = min(
                task_start_lower_bound + min_processing_time,
                effective_horizon,
            )
            task_start = model.NewIntVar(
                task_start_lower_bound,
                task_start_upper_bound,
                f"start_{task_name}",
            )
            task_end = model.NewIntVar(
                task_end_lower_bound,
                effective_horizon,
                f"end_{task_name}",
            )
            if feasible_machines_by_task is not None:
                feasible_machines = feasible_machines_by_task[task.id]
            else:
                suitable_machines = self.suitable_machines_map[task.id]
                if not suitable_machines:
                    raise ValueError(
                        f"No suitable machine found for task: {task.id}"
                    )
                feasible_machines = []
                for machine in suitable_machines:
                    free_windows = free_windows_by_machine[machine.id]
                    if (
                        self.prune_infeasible_alternatives
                        and not self._machine_can_process_task(
                            task,
                            machine,
                            free_windows,
                        )
                    ):
                        continue
                    feasible_machines.append(machine)

                if not feasible_machines:
                    raise ValueError(
                        "No feasible machine alternative found for task "
                        f"{task.id} within the current availability windows."
                    )

            single_alternative = len(feasible_machines) == 1

            task_machine = None
            if task.id in task_ids_requiring_machine_variables:
                if machine_indices is None:
                    raise ValueError(
                        "Missing machine indices for table travel model."
                    )
                if single_alternative:
                    task_machine = model.NewConstant(
                        machine_indices[feasible_machines[0].id]
                    )
                else:
                    machine_values = sorted(
                        machine_indices[machine.id]
                        for machine in feasible_machines
                    )
                    task_machine = model.NewIntVarFromDomain(
                        cp_model.Domain.FromValues(machine_values),
                        f"machine_{task_name}",
                    )

            alternatives: dict[str, _AlternativeVariables] = {}
            presences = []
            for machine in feasible_machines:
                free_windows = free_windows_by_machine[machine.id]
                processing_time = self._processing_time_on(task, machine)

                machine_name = _safe_name(machine.id)
                alternative_name = f"{task_name}_{machine_name}"
                presence: Any | None = (
                    None
                    if single_alternative
                    else model.NewBoolVar(f"presence_{alternative_name}")
                )

                relevant_unavailable_windows = []
                if task.allow_breaks:
                    relevant_unavailable_windows = (
                        self._relevant_unavailable_windows(
                            unavailable_windows_by_machine[machine.id],
                            task_start_lower_bound,
                            effective_horizon,
                        )
                    )

                if relevant_unavailable_windows:
                    max_elapsed_duration = (
                        processing_time
                        + sum(
                            window.end - window.start
                            for window in relevant_unavailable_windows
                        )
                    )
                    local_end_upper_bound = min(
                        effective_horizon,
                        task_start_upper_bound + max_elapsed_duration,
                    )
                    if single_alternative:
                        local_start = task_start
                        local_end = task_end
                    else:
                        local_start = model.NewIntVar(
                            task_start_lower_bound,
                            task_start_upper_bound,
                            f"local_start_{alternative_name}",
                        )
                        local_end = model.NewIntVar(
                            task_end_lower_bound,
                            local_end_upper_bound,
                            f"local_end_{alternative_name}",
                        )
                    break_time = self._create_break_time_var(
                        model,
                        local_start,
                        local_end,
                        relevant_unavailable_windows,
                        effective_horizon,
                        alternative_name,
                        task_start_lower_bound,
                        effective_horizon,
                    )
                    elapsed_duration_upper_bound = min(
                        max_elapsed_duration,
                        local_end_upper_bound - task_start_lower_bound,
                    )
                    elapsed_duration = model.NewIntVar(
                        processing_time,
                        elapsed_duration_upper_bound,
                        f"duration_{alternative_name}",
                    )
                    model.Add(
                        elapsed_duration == processing_time + break_time
                    )
                    if presence is None:
                        interval = model.NewIntervalVar(
                            local_start,
                            elapsed_duration,
                            local_end,
                            f"interval_{alternative_name}",
                        )
                    else:
                        interval = model.NewOptionalIntervalVar(
                            local_start,
                            elapsed_duration,
                            local_end,
                            presence,
                            f"interval_{alternative_name}",
                        )
                    self._bind_point_to_free_window(
                        model,
                        cp_model,
                        local_start,
                        presence,
                        free_windows,
                        is_start=True,
                        lower_bound=task_start_lower_bound,
                        upper_bound=task_start_upper_bound,
                    )
                    self._bind_point_to_free_window(
                        model,
                        cp_model,
                        local_end,
                        presence,
                        free_windows,
                        is_start=False,
                        lower_bound=task_end_lower_bound,
                        upper_bound=effective_horizon,
                    )
                    if presence is not None:
                        model.Add(
                            task_start == local_start
                        ).OnlyEnforceIf(presence)
                        model.Add(task_end == local_end).OnlyEnforceIf(
                            presence
                        )
                else:
                    break_time = model.NewConstant(0)
                    if presence is None:
                        interval = model.NewIntervalVar(
                            task_start,
                            processing_time,
                            task_end,
                            f"interval_{alternative_name}",
                        )
                    else:
                        interval = model.NewOptionalIntervalVar(
                            task_start,
                            processing_time,
                            task_end,
                            presence,
                            f"interval_{alternative_name}",
                        )
                    if (
                        not task.allow_breaks
                        and machine.id
                        in machines_requiring_separate_availability
                    ):
                        non_breakable_availability_intervals[
                            machine.id
                        ].append(interval)
                    if not task.allow_breaks:
                        self._bind_non_breakable_start_to_window(
                            model,
                            cp_model,
                            task_start,
                            presence,
                            free_windows,
                            processing_time,
                            lower_bound=task_start_lower_bound,
                            upper_bound=task_start_upper_bound,
                        )

                alternatives[machine.id] = _AlternativeVariables(
                    machine=machine,
                    processing_time=processing_time,
                    presence=presence,
                    interval=interval,
                    break_time=break_time,
                )
                if (
                    task_machine is not None
                    and machine_indices is not None
                    and presence is not None
                ):
                    model.Add(
                        task_machine == machine_indices[machine.id]
                    ).OnlyEnforceIf(presence)
                if presence is not None:
                    presences.append(presence)
                no_overlap_intervals[machine.id].append(interval)
                if machine_load_terms is not None:
                    if presence is None:
                        machine_load_terms[machine.id].append(
                            processing_time
                        )
                    else:
                        machine_load_terms[machine.id].append(
                            processing_time * presence
                        )

            if presences:
                model.AddExactlyOne(presences)
            task_variables[task.id] = _TaskVariables(
                task=task,
                start=task_start,
                end=task_end,
                machine=task_machine,
                alternatives=alternatives,
            )

        for intervals in no_overlap_intervals.values():
            if intervals:
                model.AddNoOverlap(intervals)
        for intervals in non_breakable_availability_intervals.values():
            if intervals:
                model.AddNoOverlap(intervals)

        self._add_dependency_constraints(
            model,
            task_variables,
            machine_indices,
        )

        makespan = model.NewIntVar(0, effective_horizon, "makespan")
        model.AddMaxEquality(
            makespan,
            [task_variable.end for task_variable in task_variables.values()],
        )
        if machine_load_terms is not None:
            for terms in machine_load_terms.values():
                if terms:
                    model.Add(makespan >= start_time + sum(terms))
        job_completion_vars: dict[str, Any] = (
            self._job_completion_variables(
                model,
                task_variables,
                effective_horizon,
            )
            if self.objective.needs_job_completion
            else {}
        )
        if heuristic_hint is not None:
            self._add_heuristic_hint(
                model,
                makespan,
                task_variables,
                heuristic_hint,
                machine_indices,
            )
        model.Minimize(
            self._objective_expression(
                model,
                makespan,
                job_completion_vars,
                effective_horizon,
            )
        )

        solver = cp_model.CpSolver()
        self._configure_solver(solver)
        status = solver.Solve(model)
        self.last_status = solver.StatusName(status)
        self.last_wall_time_seconds = solver.WallTime()

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ValueError(
                f"CP-SAT did not find a feasible schedule. "
                f"Status: {self.last_status}."
            )

        self.last_objective_value = solver.ObjectiveValue()
        self.last_best_bound = solver.BestObjectiveBound()
        scheduled_tasks: list[ScheduledTask] = []
        locked_ids = set(self.locked_tasks)
        for task in tasks:
            if task.id in locked_ids:
                continue

            task_variables_for_solution = task_variables[task.id]
            selected_alternative = next(
                alternative
                for alternative in (
                    task_variables_for_solution.alternatives.values()
                )
                if alternative.presence is None
                or solver.BooleanValue(alternative.presence)
            )
            scheduled_start = solver.Value(task_variables_for_solution.start)
            break_time = solver.Value(selected_alternative.break_time)
            scheduled_tasks.append(
                ScheduledTask(
                    start_time=scheduled_start,
                    end_time=(
                        scheduled_start
                        + selected_alternative.processing_time
                        + break_time
                    ),
                    task=task,
                    machine=selected_alternative.machine,
                    break_time=break_time,
                )
            )

        return scheduled_tasks
