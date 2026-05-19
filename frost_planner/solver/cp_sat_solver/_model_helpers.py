# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""CP-SAT model-construction helpers (intervals, dependencies).

A mixin that, combined with the BaseSolver attributes (``analysis``,
``instance``, ``locked_tasks``, etc.) and the CP-SAT configuration
flags on ``CpSatSolver``, builds intervals, bindings, and dependency
edges. Pure model-building — no orchestration, no objective shaping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from frost_planner.solver.cp_sat_solver._types import (
    _safe_name,
    _TaskVariables,
)

if TYPE_CHECKING:
    from frost_planner.core.base import Machine, SchedulingInstance, Task
    from frost_planner.core.schedule import ScheduledTask
    from frost_planner.solver.instance_analysis import (
        InstanceAnalysis,
        TimeWindow,
    )


class _ModelHelpersMixin:
    """Mixin: per-task variable creation + constraint addition.

    The mixin uses attributes / methods provided by the host class
    (``CpSatSolver`` inheriting from ``BaseSolver``).
    """

    # --- Type hints for attributes the mixin reads from self ---
    if TYPE_CHECKING:
        instance: SchedulingInstance
        locked_tasks: dict[str, ScheduledTask]
        task_id_map: dict[str, Task]
        machine_id_map: dict[str, Machine]
        analysis: InstanceAnalysis
        disjunctive_encoding: str
        travel_model: str
        hybrid_travel_threshold: int

    def _add_machine_disjunctive(
        self, model: Any, intervals: list[Any]
    ) -> None:
        """Enforce mutual exclusion on a machine using the chosen encoding."""
        if self.disjunctive_encoding == "cumulative":
            model.AddCumulative(intervals, [1] * len(intervals), 1)
        else:
            model.AddNoOverlap(intervals)

    def _add_capability_cumulatives(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        effective_horizon: int,
        start_time: int,
    ) -> None:
        """Add redundant per-capability cumulative constraints.

        For each capability c, the parallel pool M_c = {m : c in caps}
        can run at most |M_c| tasks requiring c simultaneously. We
        encode that as an AddCumulative over per-task intervals (one
        per task requiring c), with demand 1 and capacity |M_c|. The
        constraint is redundant with per-machine NoOverlap plus
        capability-requirement filtering, but CP-SAT's cumulative
        propagator can derive energetic-reasoning bounds the
        disjunctive propagator does not.
        """
        capabilities: set[str] = set()
        for variables in task_variables.values():
            capabilities.update(variables.task.requires)
        if not capabilities:
            return

        cumulative_intervals: dict[str, Any] = {}
        for task_id, variables in task_variables.items():
            if not variables.task.requires:
                continue
            cumulative_intervals[task_id] = (
                self._task_cumulative_interval(
                    model, variables, effective_horizon, start_time
                )
            )

        for capability in sorted(capabilities):
            providers = [
                machine
                for machine in self.instance.machines
                if capability in machine.capabilities
            ]
            if not providers:
                continue
            relevant_intervals = [
                cumulative_intervals[task_id]
                for task_id, variables in task_variables.items()
                if capability in variables.task.requires
                and task_id in cumulative_intervals
            ]
            if len(relevant_intervals) <= len(providers):
                continue
            model.AddCumulative(
                relevant_intervals,
                [1] * len(relevant_intervals),
                len(providers),
            )

    def _task_cumulative_interval(
        self,
        model: Any,
        variables: _TaskVariables,
        effective_horizon: int,
        start_time: int,
    ) -> Any:
        """Build a mandatory task-level interval for cumulative usage."""
        task = variables.task
        if variables.locked_machine is not None:
            scheduled = self.locked_tasks[task.id]
            size = max(0, scheduled.end_time - scheduled.start_time)
            return model.NewIntervalVar(
                variables.start,
                size,
                variables.end,
                f"cum_locked_{_safe_name(task.id)}",
            )
        min_size = self.analysis.min_processing_time(task)
        max_size = max(min_size, effective_horizon - start_time)
        size_var = model.NewIntVar(
            min_size, max_size, f"cum_size_{_safe_name(task.id)}"
        )
        model.Add(size_var == variables.end - variables.start)
        return model.NewIntervalVar(
            variables.start,
            size_var,
            variables.end,
            f"cum_{_safe_name(task.id)}",
        )

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
                    min_travel = min(travel_times)
                    extra_pair_count = sum(
                        1
                        for travel_time in travel_times
                        if travel_time > min_travel
                    )
                    use_table = (
                        extra_pair_count > self.hybrid_travel_threshold
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
        free_windows: list[TimeWindow],
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
                    "Mandatory non-breakable alternative cannot fit "
                    "within available windows during model build."
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
        free_windows: list[TimeWindow],
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
        unavailable_windows: list[TimeWindow],
        horizon: int,
        name: str,
        start_lower_bound: int,
        end_upper_bound: int,
    ) -> Any:
        """Create a variable for unavailable time inside an interval."""
        unavailable_windows = self.analysis.relevant_unavailable_windows(
            unavailable_windows,
            start_lower_bound,
            end_upper_bound,
        )
        max_break_time = sum(
            window.end - window.start for window in unavailable_windows
        )
        break_time = model.NewIntVar(
            0, max_break_time, f"{name}_break_time"
        )
        if not unavailable_windows:
            model.Add(break_time == 0)
            return break_time

        zero = model.NewConstant(0)
        overlaps = []
        for idx, window in enumerate(unavailable_windows):
            min_end = model.NewIntVar(
                0, horizon, f"{name}_min_end_{idx}"
            )
            max_start = model.NewIntVar(
                0, horizon, f"{name}_max_start_{idx}"
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
            model.AddMaxEquality(
                overlap,
                [min_end - max_start, zero],
            )
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
                    f"Locked task {task_id} is assigned to unknown "
                    f"machine {scheduled_task.machine.id}."
                )

            start = model.NewConstant(scheduled_task.start_time)
            end = model.NewConstant(scheduled_task.end_time)
            locked_variables[task_id] = _TaskVariables(
                task=scheduled_task.task,
                start=start,
                end=end,
                machine=(
                    model.NewConstant(
                        machine_indices[scheduled_task.machine.id]
                    )
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
        unavailable_windows_by_machine: dict[str, list[TimeWindow]],
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
            current_variables.start
            >= dependency_variables.end + travel_time
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
            current_variables.start
            >= dependency_variables.end + travel_var
        )

    def _add_dependency_constraints(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        machine_indices: dict[str, int] | None,
        reduced_dependencies: dict[str, list[str]],
    ) -> None:
        """Add dependencies with the configured travel formulation."""
        for task in self.analysis.all_tasks():
            current_variables = task_variables[task.id]
            for dependency_id in reduced_dependencies.get(
                task.id, list(task.dependencies)
            ):
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
                    extra_pair_count = sum(
                        1
                        for travel_time in travel_times
                        if travel_time > min_travel_time
                    )
                    use_table = (
                        extra_pair_count > self.hybrid_travel_threshold
                    )

                if use_table:
                    if machine_indices is None:
                        raise ValueError(
                            "Missing machine indices for table travel "
                            "model."
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
