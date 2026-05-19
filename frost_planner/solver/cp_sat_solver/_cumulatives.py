# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Disjunctive / cumulative constraints for the CP-SAT model.

This mixin owns the per-machine NoOverlap (or capacity-1 cumulative)
constraint and the redundant per-capability cumulative bound used by
the energetic-reasoning propagator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from frost_planner.solver.cp_sat_solver._types import (
    _safe_name,
    _TaskVariables,
)

if TYPE_CHECKING:
    from frost_planner.core.base import SchedulingInstance
    from frost_planner.core.schedule import ScheduledTask
    from frost_planner.solver.cp_sat_solver._types import CpSatOptions
    from frost_planner.solver.instance_analysis import InstanceAnalysis


class _CumulativesMixin:
    """Mixin: machine NoOverlap / Cumulative + per-capability cumulative."""

    if TYPE_CHECKING:
        instance: SchedulingInstance
        locked_tasks: dict[str, ScheduledTask]
        analysis: InstanceAnalysis
        options: CpSatOptions

    def _add_machine_disjunctive(
        self, model: Any, intervals: list[Any]
    ) -> None:
        """Enforce mutual exclusion on a machine using the chosen encoding."""
        if self.options.disjunctive_encoding == "cumulative":
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
