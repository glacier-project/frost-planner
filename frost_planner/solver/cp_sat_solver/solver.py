# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""CP-SAT solver orchestration: build the model, solve, extract."""

import sys
from dataclasses import dataclass
from typing import Any, override

from frost_planner.core.base import Machine, SchedulingInstance, Task
from frost_planner.core.objective import (
    ObjectiveWeights,
    calculate_objective_value,
)
from frost_planner.core.schedule import ScheduledTask
from frost_planner.solver.base_solver import BaseSolver
from frost_planner.solver.cp_sat_solver._cumulatives import (
    _CumulativesMixin,
)
from frost_planner.solver.cp_sat_solver._dependencies import (
    _DependenciesMixin,
)
from frost_planner.solver.cp_sat_solver._heuristic import _HeuristicMixin
from frost_planner.solver.cp_sat_solver._intervals import _IntervalsMixin
from frost_planner.solver.cp_sat_solver._objective import _ObjectiveMixin
from frost_planner.solver.cp_sat_solver._task_build import _TaskBuildMixin
from frost_planner.solver.cp_sat_solver._types import (
    CpSatOptions,
    _load_cp_model,
    _TaskVariables,
)
from frost_planner.solver.instance_analysis import TimeWindow


@dataclass
class _BoundsPhase:
    """Result of the bounds / infeasibility-check phase."""

    critical_path_starts: dict[str, int]
    critical_path_ends: dict[str, int]
    latest_starts: dict[str, int]
    latest_ends: dict[str, int]
    earliest_start_bounds: dict[str, int]


@dataclass
class _MachineSetupPhase:
    """Result of the machine-side-only setup phase."""

    machine_indices: dict[str, int] | None
    unavailable_windows_by_machine: dict[str, list[TimeWindow]]
    task_ids_requiring_machine_variables: set[str]


@dataclass
class _MachineCollectionsPhase:
    """Mutable per-machine collections plus the separated-availability set."""

    no_overlap_intervals: dict[str, list[Any]]
    non_breakable_availability_intervals: dict[str, list[Any]]
    machine_load_terms: dict[str, list[Any]] | None
    machines_requiring_separate_availability: set[str]


class CpSatSolver(
    BaseSolver,
    _IntervalsMixin,
    _DependenciesMixin,
    _CumulativesMixin,
    _TaskBuildMixin,
    _HeuristicMixin,
    _ObjectiveMixin,
):
    """CP-SAT solver for Frost Planner scheduling instances."""

    def __init__(
        self,
        instance: SchedulingInstance,
        horizon: int = sys.maxsize,
        machine_intervals: dict[str, list[tuple[int, int]]] | None = None,
        objective: ObjectiveWeights | None = None,
        *,
        options: CpSatOptions | None = None,
    ) -> None:
        super().__init__(instance, horizon, machine_intervals, objective)
        # CpSatOptions validates its own fields in __post_init__.
        self.options = options if options is not None else CpSatOptions()
        self.last_status: str | None = None
        self.last_objective_value: float | None = None
        self.last_best_bound: float | None = None
        self.last_wall_time_seconds: float | None = None
        self._last_scheduled_tasks: list[ScheduledTask] | None = None

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

        all_tasks = self.analysis.all_tasks()
        processing_time = sum(
            self.analysis.max_processing_time(task) for task in all_tasks
        )
        max_locked_end = max(
            (st.end_time for st in self.locked_tasks.values()),
            default=start_time,
        )
        travel_slack = 0
        for task in all_tasks:
            for _ in task.dependencies:
                travel_slack += max(
                    (
                        travel_time
                        for destinations in (
                            self.instance.travel_times.values()
                        )
                        for travel_time in destinations.values()
                    ),
                    default=0,
                )

        task_slack = len(all_tasks)
        return (
            max(start_time, max_locked_end)
            + processing_time
            + travel_slack
            + task_slack
        )

    def _set_num_workers(self, solver: Any) -> None:
        """Set worker count across OR-Tools parameter naming variants."""
        if self.options.num_workers is None:
            return
        if hasattr(solver.parameters, "num_workers"):
            solver.parameters.num_workers = self.options.num_workers
        else:
            solver.parameters.num_search_workers = self.options.num_workers

    def _configure_solver(self, solver: Any) -> None:
        """Apply user-provided CP-SAT search parameters."""
        if self.options.time_limit_seconds is not None:
            solver.parameters.max_time_in_seconds = (
                self.options.time_limit_seconds
            )
        self._set_num_workers(solver)
        solver.parameters.relative_gap_limit = self.options.relative_gap
        solver.parameters.log_search_progress = self.options.log_search_progress
        if self.options.random_seed is not None:
            solver.parameters.random_seed = self.options.random_seed
        if self.options.max_deterministic_time is not None:
            solver.parameters.max_deterministic_time = (
                self.options.max_deterministic_time
            )
        if self.options.linearization_level is not None:
            solver.parameters.linearization_level = (
                self.options.linearization_level
            )
        if self.options.cp_model_presolve is not None:
            solver.parameters.cp_model_presolve = self.options.cp_model_presolve
        if self.options.repair_hint:
            solver.parameters.repair_hint = True
        if self.options.optimize_with_lb_tree_search is not None:
            solver.parameters.optimize_with_lb_tree_search = (
                self.options.optimize_with_lb_tree_search
            )
        if self.options.use_objective_lb_search is not None:
            solver.parameters.use_objective_lb_search = (
                self.options.use_objective_lb_search
            )
        if self.options.cp_model_probing_level is not None:
            solver.parameters.cp_model_probing_level = (
                self.options.cp_model_probing_level
            )
        if self.options.symmetry_level is not None:
            solver.parameters.symmetry_level = self.options.symmetry_level
        if self.options.search_branching is not None:
            cp_model = _load_cp_model()
            branching_map = {
                "automatic": cp_model.AUTOMATIC_SEARCH,
                "fixed": cp_model.FIXED_SEARCH,
                "portfolio": cp_model.PORTFOLIO_SEARCH,
                "lp": cp_model.LP_SEARCH,
                "pseudo_cost": cp_model.PSEUDO_COST_SEARCH,
            }
            solver.parameters.search_branching = branching_map[
                self.options.search_branching
            ]

    @override
    def _allocate_tasks(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> list[ScheduledTask]:
        self.analysis.reset_caches()
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

        tasks = self.analysis.all_tasks()
        if not tasks:
            return []

        heuristic_hint, heuristic_objective_value, effective_horizon = (
            self._run_heuristic_phase(
                machine_intervals, effective_horizon, start_time
            )
        )

        free_windows_by_machine, feasible_machines_by_task = (
            self._build_feasibility_phase(
                tasks, machine_intervals, start_time, effective_horizon
            )
        )

        bounds = self._compute_bounds_phase(
            tasks, start_time, effective_horizon
        )

        machine_setup = self._build_machine_setup_phase(
            tasks,
            feasible_machines_by_task,
            free_windows_by_machine,
            start_time,
            effective_horizon,
        )

        machine_collections = self._build_machine_collections_phase(
            model,
            tasks,
            feasible_machines_by_task,
            machine_setup.unavailable_windows_by_machine,
            start_time,
        )

        task_variables = self._create_locked_variables(
            model,
            machine_collections.no_overlap_intervals,
            machine_setup.machine_indices,
            machine_setup.task_ids_requiring_machine_variables,
            start_time,
        )
        for task in tasks:
            if task.id in task_variables:
                continue
            task_variables[task.id] = self._build_task_variables(
                task,
                model=model,
                cp_model=cp_model,
                start_time=start_time,
                effective_horizon=effective_horizon,
                feasible_machines=feasible_machines_by_task[task.id],
                earliest_start=bounds.earliest_start_bounds[task.id],
                latest_start=bounds.latest_starts[task.id],
                latest_end=bounds.latest_ends[task.id],
                free_windows_by_machine=free_windows_by_machine,
                unavailable_windows_by_machine=(
                    machine_setup.unavailable_windows_by_machine
                ),
                machine_indices=machine_setup.machine_indices,
                task_ids_requiring_machine_variables=(
                    machine_setup.task_ids_requiring_machine_variables
                ),
                machines_requiring_separate_availability=(
                    machine_collections
                    .machines_requiring_separate_availability
                ),
                non_breakable_availability_intervals=(
                    machine_collections.non_breakable_availability_intervals
                ),
                no_overlap_intervals=(
                    machine_collections.no_overlap_intervals
                ),
                machine_load_terms=machine_collections.machine_load_terms,
            )

        self._add_disjunctive_constraints(model, machine_collections)
        if self.options.use_capability_cumulative:
            self._add_capability_cumulatives(
                model, task_variables, effective_horizon, start_time
            )
        self._add_symmetry_constraints(
            model, task_variables, free_windows_by_machine
        )
        self._add_dependency_constraints(
            model,
            task_variables,
            machine_setup.machine_indices,
            self.analysis.reduced_dependencies(),
        )

        makespan = self._build_makespan_var(
            model,
            task_variables,
            tasks,
            bounds.critical_path_ends,
            machine_collections.machine_load_terms,
            start_time,
            effective_horizon,
        )
        job_completion_vars = self._build_job_completion_with_bounds(
            model,
            task_variables,
            bounds.critical_path_ends,
            heuristic_hint,
            start_time,
            effective_horizon,
        )

        if heuristic_hint is not None:
            self._add_heuristic_hint(
                model,
                makespan,
                task_variables,
                heuristic_hint,
                machine_setup.machine_indices,
            )
        objective_expr = self._objective_expression(
            model,
            makespan,
            job_completion_vars,
            effective_horizon,
            task_variables=task_variables,
            heuristic_hint=heuristic_hint,
            critical_path_ends=bounds.critical_path_ends,
        )
        if heuristic_objective_value is not None:
            model.Add(objective_expr <= heuristic_objective_value)
        model.Minimize(objective_expr)

        self._add_decision_strategies(
            model, cp_model, task_variables, job_completion_vars
        )

        return self._solve_and_extract(model, cp_model, task_variables, tasks)

    # ----- _allocate_tasks phases ------------------------------------

    def _run_heuristic_phase(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        effective_horizon: int,
        start_time: int,
    ) -> tuple[
        dict[str, ScheduledTask] | None,
        int | None,
        int,
    ]:
        """Greedy heuristic + pure-makespan horizon shrink."""
        if not self.options.use_heuristic_hints:
            return None, None, effective_horizon
        heuristic_result = self._create_heuristic_hint(
            machine_intervals, effective_horizon, start_time
        )
        if heuristic_result is None:
            return None, None, effective_horizon
        heuristic_hint, heuristic_schedule = heuristic_result
        heuristic_objective_value = int(
            calculate_objective_value(
                heuristic_schedule, self.instance, self.objective
            )
        )
        if self.objective.is_pure_makespan:
            heuristic_makespan = max(
                scheduled_task.end_time
                for scheduled_task in heuristic_hint.values()
            )
            effective_horizon = max(
                start_time,
                min(effective_horizon, heuristic_makespan),
            )
        return heuristic_hint, heuristic_objective_value, effective_horizon

    def _build_feasibility_phase(
        self,
        tasks: list[Task],
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int,
        effective_horizon: int,
    ) -> tuple[
        dict[str, list[TimeWindow]],
        dict[str, list[Machine]],
    ]:
        """Compute free windows, then prune machine alternatives by band."""
        free_windows_by_machine = {
            machine.id: self.analysis.normalise_windows(
                machine_intervals.get(machine.id, []),
                start_time,
                effective_horizon,
            )
            for machine in self.instance.machines
        }
        # First pass: compute loose earliest/latest bounds against the
        # unpruned suitable-machines set so the band check below has a
        # safe, wider band than the eventual pruned-set bounds.
        loose_earliest_starts, _ = self.analysis.earliest_bounds(start_time)
        _, loose_latest_ends = self.analysis.latest_bounds(
            start_time, effective_horizon
        )
        feasible_machines_by_task = self.analysis.feasible_machines_by_task(
            tasks,
            free_windows_by_machine,
            prune_infeasible_alternatives=(
                self.options.prune_infeasible_alternatives
            ),
            earliest_start_by_task=loose_earliest_starts,
            latest_end_by_task=loose_latest_ends,
        )
        # Pruned-feasibility view: invalidates the stale per-lookup caches
        # the loose first pass may have populated.
        self.analysis.set_feasible_machines(feasible_machines_by_task)
        return free_windows_by_machine, feasible_machines_by_task

    def _compute_bounds_phase(
        self,
        tasks: list[Task],
        start_time: int,
        effective_horizon: int,
    ) -> _BoundsPhase:
        """Critical-path + latest-bounds + feasibility-window guard."""
        critical_path_starts, critical_path_ends = (
            self.analysis.earliest_bounds(start_time)
        )
        latest_starts, latest_ends = self.analysis.latest_bounds(
            start_time, effective_horizon
        )
        for task in tasks:
            if task.id in self.locked_tasks:
                continue
            if latest_starts[task.id] < critical_path_starts[task.id]:
                raise ValueError(
                    f"Task {task.id} is infeasible: latest_start "
                    f"{latest_starts[task.id]} < earliest_start "
                    f"{critical_path_starts[task.id]}."
                )
            cp_end = critical_path_ends.get(task.id)
            if cp_end is not None and latest_ends[task.id] < cp_end:
                raise ValueError(
                    f"Task {task.id} is infeasible: latest_end "
                    f"{latest_ends[task.id]} < earliest_end {cp_end}."
                )
        earliest_start_bounds = (
            critical_path_starts
            if self.options.use_dependency_bounds
            else {task.id: start_time for task in tasks}
        )
        return _BoundsPhase(
            critical_path_starts=critical_path_starts,
            critical_path_ends=critical_path_ends,
            latest_starts=latest_starts,
            latest_ends=latest_ends,
            earliest_start_bounds=earliest_start_bounds,
        )

    def _build_machine_setup_phase(
        self,
        tasks: list[Task],
        feasible_machines_by_task: dict[str, list[Machine]],
        free_windows_by_machine: dict[str, list[TimeWindow]],
        start_time: int,
        effective_horizon: int,
    ) -> _MachineSetupPhase:
        """Machine-index var domain + per-machine unavailable windows."""
        machine_indices = (
            {
                machine.id: index
                for index, machine in enumerate(self.instance.machines)
            }
            if self.options.travel_model in {"table", "hybrid"}
            else None
        )
        unavailable_windows_by_machine = {
            machine.id: self.analysis.unavailable_windows(
                free_windows_by_machine[machine.id],
                start_time,
                effective_horizon,
            )
            for machine in self.instance.machines
        }
        task_ids_requiring_machine_variables: set[str] = set()
        if machine_indices is not None:
            if self.options.travel_model == "hybrid":
                task_ids_requiring_machine_variables = {
                    task.id for task in tasks
                }
            else:
                task_ids_requiring_machine_variables = (
                    self._table_machine_task_ids(
                        tasks, feasible_machines_by_task
                    )
                )
        return _MachineSetupPhase(
            machine_indices=machine_indices,
            unavailable_windows_by_machine=unavailable_windows_by_machine,
            task_ids_requiring_machine_variables=(
                task_ids_requiring_machine_variables
            ),
        )

    def _build_machine_collections_phase(
        self,
        model: Any,
        tasks: list[Task],
        feasible_machines_by_task: dict[str, list[Machine]],
        unavailable_windows_by_machine: dict[str, list[TimeWindow]],
        start_time: int,
    ) -> _MachineCollectionsPhase:
        """Per-machine interval lists + load terms + availability split."""
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
            for machine in feasible_machines_by_task[task.id]:
                machines_with_breakable_alternatives.add(machine.id)
        machines_requiring_separate_availability = (
            machines_with_future_locked_tasks
            | machines_with_breakable_alternatives
        )
        machine_load_terms = self._build_machine_load_terms(start_time)
        fixed_unavailable_intervals = (
            self._create_fixed_unavailable_intervals(
                model, unavailable_windows_by_machine
            )
        )
        non_breakable_availability_intervals: dict[str, list[Any]] = {
            machine.id: [] for machine in self.instance.machines
        }
        for machine in self.instance.machines:
            target = (
                non_breakable_availability_intervals
                if machine.id in machines_requiring_separate_availability
                else no_overlap_intervals
            )
            target[machine.id].extend(fixed_unavailable_intervals[machine.id])
        return _MachineCollectionsPhase(
            no_overlap_intervals=no_overlap_intervals,
            non_breakable_availability_intervals=(
                non_breakable_availability_intervals
            ),
            machine_load_terms=machine_load_terms,
            machines_requiring_separate_availability=(
                machines_requiring_separate_availability
            ),
        )

    def _build_machine_load_terms(
        self, start_time: int
    ) -> dict[str, list[Any]] | None:
        """Seed per-machine load with the locked-task contributions."""
        if not self.options.use_machine_load_bounds:
            return None
        machine_load_terms: dict[str, list[Any]] = {
            machine.id: [] for machine in self.instance.machines
        }
        for scheduled_task in self.locked_tasks.values():
            if scheduled_task.task.id not in self.task_id_map:
                continue
            if scheduled_task.machine.id not in machine_load_terms:
                raise ValueError(
                    f"Locked task {scheduled_task.task.id} is "
                    f"assigned to unknown machine "
                    f"{scheduled_task.machine.id}."
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
        return machine_load_terms

    def _add_disjunctive_constraints(
        self,
        model: Any,
        collections: _MachineCollectionsPhase,
    ) -> None:
        """Apply per-machine NoOverlap (or capacity-1 cumulative)."""
        for intervals in collections.no_overlap_intervals.values():
            if intervals:
                self._add_machine_disjunctive(model, intervals)
        for intervals in (
            collections.non_breakable_availability_intervals.values()
        ):
            if intervals:
                self._add_machine_disjunctive(model, intervals)

    def _add_symmetry_constraints(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        free_windows_by_machine: dict[str, list[TimeWindow]],
    ) -> None:
        """Break identical-machine and identical-job symmetries."""
        for group in self.analysis.identical_machine_groups(
            free_windows_by_machine
        ):
            counts: list[Any] = []
            for machine in group:
                presence_terms = [
                    alternative.presence
                    for variables in task_variables.values()
                    if (
                        alternative := variables.alternatives.get(machine.id)
                    )
                    is not None
                    and alternative.presence is not None
                ]
                counts.append(
                    sum(presence_terms) if presence_terms else 0
                )
            for index in range(len(counts) - 1):
                model.Add(counts[index] >= counts[index + 1])

        for job_group in self.analysis.identical_job_groups():
            entry_starts = [
                task_variables[job.tasks[0].id].start
                for job in job_group
                if job.tasks and job.tasks[0].id in task_variables
            ]
            for index in range(len(entry_starts) - 1):
                model.Add(entry_starts[index] <= entry_starts[index + 1])

    def _build_makespan_var(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        tasks: list[Task],
        critical_path_ends: dict[str, int],
        machine_load_terms: dict[str, list[Any]] | None,
        start_time: int,
        effective_horizon: int,
    ) -> Any | None:
        """Build the makespan IntVar + critical-path / capability LBs."""
        if not (
            self.objective.makespan or self.options.use_machine_load_bounds
        ):
            return None
        makespan = model.NewIntVar(0, effective_horizon, "makespan")
        model.AddMaxEquality(
            makespan,
            [
                task_variable.end
                for task_variable in task_variables.values()
            ],
        )
        if machine_load_terms is not None:
            for terms in machine_load_terms.values():
                if terms:
                    model.Add(makespan >= start_time + sum(terms))
        critical_path_makespan_lb = max(
            (
                critical_path_ends[task.id]
                for task in tasks
                if task.id in critical_path_ends
            ),
            default=start_time,
        )
        if critical_path_makespan_lb > start_time:
            model.Add(makespan >= critical_path_makespan_lb)
        for bottleneck_lb in self.analysis.capability_bottleneck_lower_bounds(
            start_time
        ):
            if bottleneck_lb > start_time:
                model.Add(makespan >= bottleneck_lb)
        return makespan

    def _build_job_completion_with_bounds(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        critical_path_ends: dict[str, int],
        heuristic_hint: dict[str, ScheduledTask] | None,
        start_time: int,
        effective_horizon: int,
    ) -> dict[str, Any]:
        """Build job-completion vars + per-job/per-task critical-path LBs."""
        job_completion_vars: dict[str, Any] = (
            self._job_completion_variables(
                model, task_variables, effective_horizon, heuristic_hint
            )
            if self.objective.needs_job_completion
            else {}
        )
        for job in self.instance.jobs:
            job_critical_path_lb = max(
                (
                    critical_path_ends[task.id]
                    for task in job.tasks
                    if task.id in critical_path_ends
                ),
                default=start_time,
            )
            if job_critical_path_lb <= start_time:
                continue
            if job.id in job_completion_vars:
                model.Add(
                    job_completion_vars[job.id] >= job_critical_path_lb
                )
            # Item #47: per-job analogue of item #9's global makespan
            # LB, applied to every task's `end` regardless of whether
            # this job builds a completion variable. The IntVar already
            # carries this as a domain lower bound when
            # use_dependency_bounds is on, but the explicit constraint
            # lets CP-SAT use it at branching, not just at variable
            # build.
            for task in job.tasks:
                if task.id not in task_variables:
                    continue
                task_lb = critical_path_ends.get(task.id)
                if task_lb is None or task_lb <= start_time:
                    continue
                if task.id in self.locked_tasks:
                    continue
                model.Add(task_variables[task.id].end >= task_lb)
        return job_completion_vars

    def _add_decision_strategies(
        self,
        model: Any,
        cp_model: Any,
        task_variables: dict[str, _TaskVariables],
        job_completion_vars: dict[str, Any],
    ) -> None:
        """Optional CP-SAT decision strategies (presences/starts/etc.)."""
        if not self.options.use_search_strategy:
            return
        presence_vars = [
            alternative.presence
            for task_variables_entry in task_variables.values()
            for alternative in (
                task_variables_entry.alternatives.values()
            )
            if alternative.presence is not None
        ]
        if presence_vars:
            model.AddDecisionStrategy(
                presence_vars,
                cp_model.CHOOSE_FIRST,
                cp_model.SELECT_MAX_VALUE,
            )
        start_vars = [
            task_variables_entry.start
            for task_variables_entry in task_variables.values()
        ]
        if start_vars:
            model.AddDecisionStrategy(
                start_vars,
                cp_model.CHOOSE_FIRST,
                cp_model.SELECT_MIN_VALUE,
            )
        if self.objective.needs_job_completion and job_completion_vars:
            completion_vars = list(job_completion_vars.values())
            if completion_vars:
                model.AddDecisionStrategy(
                    completion_vars,
                    cp_model.CHOOSE_FIRST,
                    cp_model.SELECT_MIN_VALUE,
                )

    def _solve_and_extract(
        self,
        model: Any,
        cp_model: Any,
        task_variables: dict[str, _TaskVariables],
        tasks: list[Task],
    ) -> list[ScheduledTask]:
        """Run the solver and read back the scheduled tasks."""
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
            scheduled_start = solver.Value(
                task_variables_for_solution.start
            )
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
        # Cache the full schedule (locked + scheduled) for warm-starts
        # on the next solve.
        locked_scheduled = [
            scheduled_task
            for scheduled_task in self.locked_tasks.values()
            if scheduled_task.task.id in self.task_id_map
        ]
        self._last_scheduled_tasks = locked_scheduled + scheduled_tasks
        return scheduled_tasks
