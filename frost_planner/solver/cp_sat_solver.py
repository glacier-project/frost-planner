# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys
from dataclasses import dataclass
from typing import Any, override

from frost_planner.core.base import Machine, SchedulingInstance, Task
from frost_planner.core.schedule import ScheduledTask
from frost_planner.solver.base_solver import BaseSolver


@dataclass(frozen=True)
class _TimeWindow:
    """Closed-open integer time window."""

    start: int
    end: int


@dataclass
class _AlternativeVariables:
    """Variables for one task-machine assignment alternative."""

    machine: Machine
    presence: Any
    interval: Any
    break_time: Any


@dataclass
class _TaskVariables:
    """Variables for one task in the CP-SAT model."""

    task: Task
    start: Any
    end: Any
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
        num_workers: int | None = None,
        relative_gap: float = 0.0,
        log_search_progress: bool = False,
    ) -> None:
        super().__init__(instance, horizon, machine_intervals)
        if num_workers is not None and num_workers < 1:
            raise ValueError("num_workers must be positive.")
        if relative_gap < 0:
            raise ValueError("relative_gap must be non-negative.")

        self.time_limit_seconds = time_limit_seconds
        self.num_workers = num_workers
        self.relative_gap = relative_gap
        self.log_search_progress = log_search_progress
        self.last_status: str | None = None
        self.last_objective_value: float | None = None
        self.last_best_bound: float | None = None
        self.last_wall_time_seconds: float | None = None

    def _all_tasks(self) -> list[Task]:
        """Return all tasks in instance order."""
        return [task for job in self.instance.jobs for task in job.tasks]

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
            task.processing_time for task in self._all_tasks()
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

    def _bind_interval_to_free_window(
        self,
        model: Any,
        start: Any,
        end: Any,
        presence: Any,
        free_windows: list[_TimeWindow],
        processing_time: int,
        name: str,
    ) -> None:
        """Force a present interval to fit inside one free window."""
        feasible_windows = [
            window
            for window in free_windows
            if window.end - window.start >= processing_time
        ]
        if not feasible_windows:
            model.Add(presence == 0)
            return

        window_literals = []
        for idx, window in enumerate(feasible_windows):
            literal = model.NewBoolVar(f"{name}_window_{idx}")
            model.Add(start >= window.start).OnlyEnforceIf(literal)
            model.Add(end <= window.end).OnlyEnforceIf(literal)
            model.AddImplication(literal, presence)
            window_literals.append(literal)

        model.Add(sum(window_literals) == presence)

    def _bind_point_to_free_window(
        self,
        model: Any,
        value: Any,
        presence: Any,
        free_windows: list[_TimeWindow],
        name: str,
        *,
        is_start: bool,
    ) -> None:
        """Force a present start or end point to lie on available time."""
        if not free_windows:
            model.Add(presence == 0)
            return

        window_literals = []
        for idx, window in enumerate(free_windows):
            literal = model.NewBoolVar(f"{name}_window_{idx}")
            model.Add(value >= window.start).OnlyEnforceIf(literal)
            if is_start:
                model.Add(value < window.end).OnlyEnforceIf(literal)
            else:
                model.Add(value <= window.end).OnlyEnforceIf(literal)
            model.AddImplication(literal, presence)
            window_literals.append(literal)

        model.Add(sum(window_literals) == presence)

    def _create_break_time_var(
        self,
        model: Any,
        start: Any,
        end: Any,
        unavailable_windows: list[_TimeWindow],
        horizon: int,
        name: str,
    ) -> Any:
        """Create a variable for unavailable time inside an interval."""
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

    def _add_dependency_constraints(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
    ) -> None:
        """Add precedence and machine-dependent travel constraints."""
        for task in self._all_tasks():
            current_variables = task_variables[task.id]
            for dependency_id in task.dependencies:
                if dependency_id not in task_variables:
                    raise ValueError(
                        f"Task {task.id} depends on unknown task "
                        f"{dependency_id}."
                    )

                dependency_variables = task_variables[dependency_id]
                for dependency_machine, dependency_presence in (
                    self._machine_choices(dependency_variables)
                ):
                    for current_machine, current_presence in (
                        self._machine_choices(current_variables)
                    ):
                        travel_time = self.instance.get_travel_time(
                            dependency_machine,
                            current_machine,
                        )
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
        no_overlap_intervals: dict[str, list[Any]] = {
            machine.id: [] for machine in self.instance.machines
        }
        task_variables = self._create_locked_variables(
            model,
            no_overlap_intervals,
            start_time,
        )

        for task in tasks:
            if task.id in task_variables:
                continue

            task_name = _safe_name(task.id)
            task_start = model.NewIntVar(
                start_time,
                effective_horizon,
                f"start_{task_name}",
            )
            task_end = model.NewIntVar(
                start_time,
                effective_horizon,
                f"end_{task_name}",
            )
            alternatives: dict[str, _AlternativeVariables] = {}
            presences = []
            suitable_machines = self.suitable_machines_map[task.id]
            if not suitable_machines:
                raise ValueError(
                    f"No suitable machine found for task: {task.id}"
                )

            for machine in suitable_machines:
                machine_name = _safe_name(machine.id)
                alternative_name = f"{task_name}_{machine_name}"
                presence = model.NewBoolVar(f"presence_{alternative_name}")
                local_start = model.NewIntVar(
                    start_time,
                    effective_horizon,
                    f"local_start_{alternative_name}",
                )
                local_end = model.NewIntVar(
                    start_time,
                    effective_horizon,
                    f"local_end_{alternative_name}",
                )
                free_windows = free_windows_by_machine[machine.id]

                if task.allow_breaks:
                    break_time = self._create_break_time_var(
                        model,
                        local_start,
                        local_end,
                        unavailable_windows_by_machine[machine.id],
                        effective_horizon,
                        alternative_name,
                    )
                    elapsed_duration = model.NewIntVar(
                        task.processing_time,
                        effective_horizon,
                        f"duration_{alternative_name}",
                    )
                    model.Add(
                        elapsed_duration == task.processing_time + break_time
                    )
                    interval = model.NewOptionalIntervalVar(
                        local_start,
                        elapsed_duration,
                        local_end,
                        presence,
                        f"interval_{alternative_name}",
                    )
                    self._bind_point_to_free_window(
                        model,
                        local_start,
                        presence,
                        free_windows,
                        f"start_window_{alternative_name}",
                        is_start=True,
                    )
                    self._bind_point_to_free_window(
                        model,
                        local_end,
                        presence,
                        free_windows,
                        f"end_window_{alternative_name}",
                        is_start=False,
                    )
                else:
                    break_time = model.NewConstant(0)
                    interval = model.NewOptionalIntervalVar(
                        local_start,
                        task.processing_time,
                        local_end,
                        presence,
                        f"interval_{alternative_name}",
                    )
                    self._bind_interval_to_free_window(
                        model,
                        local_start,
                        local_end,
                        presence,
                        free_windows,
                        task.processing_time,
                        f"window_{alternative_name}",
                    )

                model.Add(task_start == local_start).OnlyEnforceIf(presence)
                model.Add(task_end == local_end).OnlyEnforceIf(presence)
                alternatives[machine.id] = _AlternativeVariables(
                    machine=machine,
                    presence=presence,
                    interval=interval,
                    break_time=break_time,
                )
                presences.append(presence)
                no_overlap_intervals[machine.id].append(interval)

            model.AddExactlyOne(presences)
            task_variables[task.id] = _TaskVariables(
                task=task,
                start=task_start,
                end=task_end,
                alternatives=alternatives,
            )

        for intervals in no_overlap_intervals.values():
            if intervals:
                model.AddNoOverlap(intervals)

        self._add_dependency_constraints(model, task_variables)

        makespan = model.NewIntVar(0, effective_horizon, "makespan")
        model.AddMaxEquality(
            makespan,
            [task_variable.end for task_variable in task_variables.values()],
        )
        model.Minimize(makespan)

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
                if solver.BooleanValue(alternative.presence)
            )
            scheduled_start = solver.Value(task_variables_for_solution.start)
            break_time = solver.Value(selected_alternative.break_time)
            scheduled_tasks.append(
                ScheduledTask(
                    start_time=scheduled_start,
                    end_time=(
                        scheduled_start + task.processing_time + break_time
                    ),
                    task=task,
                    machine=selected_alternative.machine,
                    break_time=break_time,
                )
            )

        return scheduled_tasks
