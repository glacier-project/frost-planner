# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Interval / window construction helpers for the CP-SAT model.

This mixin owns everything that builds CP-SAT IntervalVars and the
domain bindings that pin task starts/ends onto machine free-windows:

* ``_create_locked_variables`` — fixed intervals for already-locked tasks
* ``_create_fixed_unavailable_intervals`` — per-machine constant intervals
  for unavailable windows
* ``_create_break_time_var`` — per-alternative break-time IntVar that
  sums overlaps with unavailable windows
* ``_bind_point_to_free_window`` / ``_bind_non_breakable_start_to_window``
  — restrict a start/end variable to lie on available time
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


class _IntervalsMixin:
    """Mixin: build the per-task and per-window IntervalVars."""

    if TYPE_CHECKING:
        instance: SchedulingInstance
        locked_tasks: dict[str, ScheduledTask]
        task_id_map: dict[str, Task]
        machine_id_map: dict[str, Machine]
        analysis: InstanceAnalysis

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
        break_time = model.NewIntVar(0, max_break_time, f"{name}_break_time")
        if not unavailable_windows:
            model.Add(break_time == 0)
            return break_time

        zero = model.NewConstant(0)
        overlaps = []
        for idx, window in enumerate(unavailable_windows):
            min_end = model.NewIntVar(0, horizon, f"{name}_min_end_{idx}")
            max_start = model.NewIntVar(0, horizon, f"{name}_max_start_{idx}")
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
