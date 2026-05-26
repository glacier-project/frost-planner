# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Per-task variable + alternative construction for the CP-SAT model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from frost_planner.solver.cp_sat_solver._types import (
    _AlternativeVariables,
    _safe_name,
    _TaskVariables,
)

if TYPE_CHECKING:
    from frost_planner.core.base import Machine, SchedulingInstance, Task
    from frost_planner.solver.cp_sat_solver._types import CpSatOptions
    from frost_planner.solver.instance_analysis import (
        InstanceAnalysis,
        TimeWindow,
    )


@dataclass
class _TaskBuildContext:
    """Shared state across every task built in one ``_allocate_tasks`` call.

    Captures CP-SAT model handles, time bounds, and per-machine lookup
    tables. The three list-valued fields at the bottom are the append
    targets that each task contributes intervals / load terms to.
    """

    model: Any
    cp_model: Any
    start_time: int
    effective_horizon: int
    free_windows_by_machine: dict[str, list[TimeWindow]]
    unavailable_windows_by_machine: dict[str, list[TimeWindow]]
    machine_indices: dict[str, int] | None
    task_ids_requiring_machine_variables: set[str]
    machines_requiring_separate_availability: set[str]
    non_breakable_availability_intervals: dict[str, list[Any]]
    no_overlap_intervals: dict[str, list[Any]]
    machine_load_terms: dict[str, list[Any]] | None


@dataclass
class _TaskBuildBounds:
    """Per-task feasibility band fed into ``_build_task_variables``."""

    feasible_machines: list[Machine]
    earliest_start: int
    latest_start: int
    latest_end: int


class _TaskBuildMixin:
    """Mixin: build the variables, alternatives, and intervals for one task."""

    if TYPE_CHECKING:
        instance: SchedulingInstance
        analysis: InstanceAnalysis
        options: CpSatOptions

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
        ) -> Any: ...

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
        ) -> None: ...

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
        ) -> None: ...

    def _build_task_variables(
        self,
        task: Task,
        ctx: _TaskBuildContext,
        bounds: _TaskBuildBounds,
    ) -> _TaskVariables:
        """Build start/end + alternative variables for one non-locked task.

        Mutates ``ctx.no_overlap_intervals``,
        ``ctx.non_breakable_availability_intervals``, and (when set)
        ``ctx.machine_load_terms`` by appending the intervals and load
        contributions produced for ``task``.
        """
        task_name = _safe_name(task.id)
        min_processing_time = self.analysis.min_processing_time(task)
        task_start_lower_bound = min(
            max(ctx.start_time, bounds.earliest_start),
            ctx.effective_horizon,
        )
        task_start_upper_bound = max(
            task_start_lower_bound,
            min(
                ctx.effective_horizon - min_processing_time,
                bounds.latest_start,
            ),
        )
        task_end_lower_bound = min(
            task_start_lower_bound + min_processing_time,
            ctx.effective_horizon,
        )
        task_end_upper_bound = max(
            task_end_lower_bound,
            min(ctx.effective_horizon, bounds.latest_end),
        )
        task_start = ctx.model.NewIntVar(
            task_start_lower_bound,
            task_start_upper_bound,
            f"start_{task_name}",
        )
        task_end = ctx.model.NewIntVar(
            task_end_lower_bound,
            task_end_upper_bound,
            f"end_{task_name}",
        )

        single_alternative = len(bounds.feasible_machines) == 1
        task_machine = self._build_task_machine_var(
            model=ctx.model,
            cp_model=ctx.cp_model,
            task_name=task_name,
            feasible_machines=bounds.feasible_machines,
            machine_indices=ctx.machine_indices,
            include_task_machine_var=(
                task.id in ctx.task_ids_requiring_machine_variables
            ),
            single_alternative=single_alternative,
        )

        alternatives: dict[str, _AlternativeVariables] = {}
        presences: list[Any] = []
        for machine in bounds.feasible_machines:
            alternative = self._build_alternative(
                task=task,
                machine=machine,
                ctx=ctx,
                task_start=task_start,
                task_end=task_end,
                task_start_lower_bound=task_start_lower_bound,
                task_start_upper_bound=task_start_upper_bound,
                task_end_lower_bound=task_end_lower_bound,
                task_end_upper_bound=task_end_upper_bound,
                single_alternative=single_alternative,
            )
            alternatives[machine.id] = alternative
            if (
                task_machine is not None
                and ctx.machine_indices is not None
                and alternative.presence is not None
            ):
                ctx.model.Add(
                    task_machine == ctx.machine_indices[machine.id]
                ).OnlyEnforceIf(alternative.presence)
            if alternative.presence is not None:
                presences.append(alternative.presence)
            ctx.no_overlap_intervals[machine.id].append(alternative.interval)
            if ctx.machine_load_terms is not None:
                term = (
                    alternative.processing_time
                    if alternative.presence is None
                    else alternative.processing_time * alternative.presence
                )
                ctx.machine_load_terms[machine.id].append(term)

        if presences:
            ctx.model.AddExactlyOne(presences)
        return _TaskVariables(
            task=task,
            start=task_start,
            end=task_end,
            machine=task_machine,
            alternatives=alternatives,
        )

    def _build_task_machine_var(
        self,
        *,
        model: Any,
        cp_model: Any,
        task_name: str,
        feasible_machines: list[Machine],
        machine_indices: dict[str, int] | None,
        include_task_machine_var: bool,
        single_alternative: bool,
    ) -> Any | None:
        """Build the task-level machine-index var (table/hybrid travel only)."""
        if not include_task_machine_var:
            return None
        if machine_indices is None:
            raise ValueError("Missing machine indices for table travel model.")
        if single_alternative:
            return model.NewConstant(machine_indices[feasible_machines[0].id])
        machine_values = sorted(
            machine_indices[machine.id] for machine in feasible_machines
        )
        return model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(machine_values),
            f"machine_{task_name}",
        )

    def _build_alternative(
        self,
        *,
        task: Task,
        machine: Machine,
        ctx: _TaskBuildContext,
        task_start: Any,
        task_end: Any,
        task_start_lower_bound: int,
        task_start_upper_bound: int,
        task_end_lower_bound: int,
        task_end_upper_bound: int,
        single_alternative: bool,
    ) -> _AlternativeVariables:
        """Build one (task, machine) alternative's variables and intervals."""
        processing_time = self.analysis.processing_time_on(task, machine)
        task_name = _safe_name(task.id)
        machine_name = _safe_name(machine.id)
        alternative_name = f"{task_name}_{machine_name}"
        presence: Any | None = (
            None
            if single_alternative
            else ctx.model.NewBoolVar(f"presence_{alternative_name}")
        )

        relevant_unavailable_windows: list[TimeWindow] = []
        if task.allow_breaks:
            # The task's actual occupancy is bounded above by
            # task_end_upper_bound (= min(effective_horizon,
            # latest_end[task])); windows starting at or after that bound
            # cannot overlap. Restricting the filter here tightens
            # max_break_time / max_elapsed_duration / local_end_upper_bound
            # without changing semantics.
            relevant_unavailable_windows = (
                self.analysis.relevant_unavailable_windows(
                    ctx.unavailable_windows_by_machine[machine.id],
                    task_start_lower_bound,
                    task_end_upper_bound,
                    machine_id=machine.id,
                )
            )

        free_windows = ctx.free_windows_by_machine[machine.id]
        if relevant_unavailable_windows:
            interval, break_time = self._build_breakable_alternative(
                ctx=ctx,
                task_start=task_start,
                task_end=task_end,
                presence=presence,
                processing_time=processing_time,
                alternative_name=alternative_name,
                single_alternative=single_alternative,
                task_start_lower_bound=task_start_lower_bound,
                task_start_upper_bound=task_start_upper_bound,
                task_end_lower_bound=task_end_lower_bound,
                task_end_upper_bound=task_end_upper_bound,
                free_windows=free_windows,
                relevant_unavailable_windows=relevant_unavailable_windows,
            )
        else:
            interval, break_time = self._build_non_breakable_alternative(
                ctx=ctx,
                task=task,
                machine=machine,
                task_start=task_start,
                task_end=task_end,
                presence=presence,
                processing_time=processing_time,
                alternative_name=alternative_name,
                task_start_lower_bound=task_start_lower_bound,
                task_start_upper_bound=task_start_upper_bound,
                free_windows=free_windows,
            )

        return _AlternativeVariables(
            machine=machine,
            processing_time=processing_time,
            presence=presence,
            interval=interval,
            break_time=break_time,
        )

    def _build_breakable_alternative(
        self,
        *,
        ctx: _TaskBuildContext,
        task_start: Any,
        task_end: Any,
        presence: Any | None,
        processing_time: int,
        alternative_name: str,
        single_alternative: bool,
        task_start_lower_bound: int,
        task_start_upper_bound: int,
        task_end_lower_bound: int,
        task_end_upper_bound: int,
        free_windows: list[TimeWindow],
        relevant_unavailable_windows: list[TimeWindow],
    ) -> tuple[Any, Any]:
        """Build the breakable-task interval (start/end may include breaks)."""
        model = ctx.model
        max_elapsed_duration = processing_time + sum(
            window.end - window.start for window in relevant_unavailable_windows
        )
        local_end_upper_bound = min(
            task_end_upper_bound,
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
            ctx.effective_horizon,
            alternative_name,
            task_start_lower_bound,
            task_end_upper_bound,
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
        model.Add(elapsed_duration == processing_time + break_time)
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
            ctx.cp_model,
            local_start,
            presence,
            free_windows,
            is_start=True,
            lower_bound=task_start_lower_bound,
            upper_bound=task_start_upper_bound,
        )
        self._bind_point_to_free_window(
            model,
            ctx.cp_model,
            local_end,
            presence,
            free_windows,
            is_start=False,
            lower_bound=task_end_lower_bound,
            upper_bound=ctx.effective_horizon,
        )
        if presence is not None:
            model.Add(task_start == local_start).OnlyEnforceIf(presence)
            model.Add(task_end == local_end).OnlyEnforceIf(presence)
        return interval, break_time

    def _build_non_breakable_alternative(
        self,
        *,
        ctx: _TaskBuildContext,
        task: Task,
        machine: Machine,
        task_start: Any,
        task_end: Any,
        presence: Any | None,
        processing_time: int,
        alternative_name: str,
        task_start_lower_bound: int,
        task_start_upper_bound: int,
        free_windows: list[TimeWindow],
    ) -> tuple[Any, Any]:
        """Build a contiguous (no-break) alternative interval."""
        model = ctx.model
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
            and machine.id in ctx.machines_requiring_separate_availability
        ):
            ctx.non_breakable_availability_intervals[machine.id].append(
                interval
            )
        if not task.allow_breaks:
            self._bind_non_breakable_start_to_window(
                model,
                ctx.cp_model,
                task_start,
                presence,
                free_windows,
                processing_time,
                lower_bound=task_start_lower_bound,
                upper_bound=task_start_upper_bound,
            )
        return interval, break_time
