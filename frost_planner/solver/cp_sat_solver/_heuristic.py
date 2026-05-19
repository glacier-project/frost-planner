# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Heuristic incumbent construction and hint injection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from frost_planner.core.objective import calculate_objective_value
from frost_planner.core.validate import validate_schedule
from frost_planner.solver.greedy import _create_schedule

if TYPE_CHECKING:
    from frost_planner.core.base import Job, SchedulingInstance
    from frost_planner.core.objective import ObjectiveWeights
    from frost_planner.core.schedule import Schedule, ScheduledTask
    from frost_planner.solver.base_solver import _GreedyResult
    from frost_planner.solver.cp_sat_solver._types import _TaskVariables
    from frost_planner.solver.instance_analysis import InstanceAnalysis


class _HeuristicMixin:
    """Mixin: candidate-ordering search + CP-SAT hint application."""

    if TYPE_CHECKING:
        instance: SchedulingInstance
        objective: ObjectiveWeights
        analysis: InstanceAnalysis
        _last_scheduled_tasks: list[ScheduledTask] | None

        def _greedy_evaluate(
            self,
            jobs: list[Job],
            machine_intervals: dict[str, list[tuple[int, int]]],
            *,
            start_time: int = ...,
            horizon: int | None = ...,
            copy_intervals: bool = ...,
        ) -> _GreedyResult: ...

    def _evaluate_ordering(
        self,
        ordering: list[Job],
        machine_intervals: dict[str, list[tuple[int, int]]],
        effective_horizon: int,
        start_time: int,
    ) -> tuple[float, dict[str, ScheduledTask], Schedule] | None:
        """Greedy-schedule one ordering and return its objective value."""
        try:
            result = self._greedy_evaluate(
                ordering,
                machine_intervals,
                start_time=start_time,
                horizon=effective_horizon,
            )
        except (KeyError, ValueError):
            return None
        if not validate_schedule(result.schedule, self.instance):
            return None
        hint_map = {
            scheduled_task.task.id: scheduled_task
            for scheduled_task in result.scheduled_tasks
        }
        return result.objective, hint_map, result.schedule

    def _create_heuristic_hint(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        effective_horizon: int,
        start_time: int,
    ) -> tuple[dict[str, ScheduledTask], Schedule] | None:
        """Pick the best greedy schedule across several job orderings."""
        best_objective: float | None = None
        best_ordering: list[Job] | None = None
        best_result: tuple[dict[str, ScheduledTask], Schedule] | None = (
            None
        )

        if self._last_scheduled_tasks is not None:
            try:
                warm_schedule = _create_schedule(
                    scheduled_tasks=self._last_scheduled_tasks,
                    machines=self.instance.machines,
                )
                if validate_schedule(warm_schedule, self.instance):
                    warm_obj = calculate_objective_value(
                        warm_schedule, self.instance, self.objective
                    )
                    best_objective = warm_obj
                    best_result = (
                        {
                            scheduled_task.task.id: scheduled_task
                            for scheduled_task in self._last_scheduled_tasks
                        },
                        warm_schedule,
                    )
            except (KeyError, ValueError):
                self._last_scheduled_tasks = None

        for ordering in self.analysis.candidate_job_orderings():
            evaluation = self._evaluate_ordering(
                ordering,
                machine_intervals,
                effective_horizon,
                start_time,
            )
            if evaluation is None:
                continue
            candidate_objective, hint_map, schedule = evaluation
            if (
                best_objective is None
                or candidate_objective < best_objective
            ):
                best_objective = candidate_objective
                best_ordering = ordering
                best_result = (hint_map, schedule)
        if best_ordering is None or best_result is None:
            return best_result

        current = list(best_ordering)
        current_objective = best_objective
        for index in range(len(current) - 1):
            swapped = list(current)
            swapped[index], swapped[index + 1] = (
                swapped[index + 1],
                swapped[index],
            )
            evaluation = self._evaluate_ordering(
                swapped,
                machine_intervals,
                effective_horizon,
                start_time,
            )
            if evaluation is None:
                continue
            candidate_objective, hint_map, schedule = evaluation
            if (
                current_objective is not None
                and candidate_objective < current_objective
            ):
                current_objective = candidate_objective
                current = swapped
                best_result = (hint_map, schedule)
        return best_result

    def _add_heuristic_hint(
        self,
        model: Any,
        makespan: Any | None,
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

        if makespan is not None:
            heuristic_makespan = max(
                scheduled_task.end_time for scheduled_task in hinted_tasks
            )
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
