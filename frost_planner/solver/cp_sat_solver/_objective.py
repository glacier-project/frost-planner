# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Objective expression and job-completion variable construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from frost_planner.solver.cp_sat_solver._types import _safe_name

if TYPE_CHECKING:
    from frost_planner.core.base import Job, SchedulingInstance
    from frost_planner.core.objective import ObjectiveWeights
    from frost_planner.core.schedule import ScheduledTask
    from frost_planner.solver.cp_sat_solver._types import _TaskVariables


class _ObjectiveMixin:
    """Mixin: builds the weighted objective expression and its IntVars."""

    if TYPE_CHECKING:
        instance: SchedulingInstance
        objective: ObjectiveWeights

    def _job_completion_variables(
        self,
        model: Any,
        task_variables: dict[str, _TaskVariables],
        horizon: int,
        heuristic_hint: dict[str, ScheduledTask] | None = None,
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
            if len(job_task_ends) == 1:
                job_completion_vars[job.id] = job_task_ends[0]
                continue

            job_completion = model.NewIntVar(
                0,
                horizon,
                f"job_end_{_safe_name(job.id)}",
            )
            model.AddMaxEquality(job_completion, job_task_ends)
            if heuristic_hint is not None:
                hint_value = self._heuristic_job_completion(
                    job, task_variables, heuristic_hint
                )
                if hint_value is not None:
                    model.AddHint(job_completion, hint_value)
            job_completion_vars[job.id] = job_completion
        return job_completion_vars

    def _heuristic_job_completion(
        self,
        job: Job,
        task_variables: dict[str, _TaskVariables],
        heuristic_hint: dict[str, ScheduledTask],
    ) -> int | None:
        """Return the heuristic job-completion value for AddHint, or None."""
        end_times = [
            heuristic_hint[task.id].end_time
            for task in job.tasks
            if task.id in task_variables and task.id in heuristic_hint
        ]
        if not end_times:
            return None
        return max(end_times)

    def _objective_expression(
        self,
        model: Any,
        makespan: Any | None,
        job_completion_vars: dict[str, Any],
        horizon: int,
        task_variables: dict[str, _TaskVariables] | None = None,
        heuristic_hint: dict[str, ScheduledTask] | None = None,
        critical_path_ends: dict[str, int] | None = None,
    ) -> Any:
        """Build the configured CP-SAT objective expression."""
        terms = []
        objective = self.objective
        if objective.makespan and makespan is not None:
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
        per_job_tardiness_hints: list[int] = []
        max_tardiness_upper_bound = 0
        if needs_per_job_term:
            for job in self.instance.jobs:
                if job.due_date is None:
                    continue

                job_name = _safe_name(job.id)
                completion = job_completion_vars[job.id]
                heuristic_completion: int | None = None
                if heuristic_hint is not None and task_variables is not None:
                    heuristic_completion = self._heuristic_job_completion(
                        job, task_variables, heuristic_hint
                    )

                # Tightened per-job bounds derived from the per-task
                # critical-path completion lower bounds.
                job_completion_lower_bound = 0
                if critical_path_ends is not None:
                    job_completion_lower_bound = max(
                        (
                            critical_path_ends[task.id]
                            for task in job.tasks
                            if task.id in critical_path_ends
                        ),
                        default=0,
                    )
                tardiness_lower_bound = max(
                    0, job_completion_lower_bound - job.due_date
                )
                tardiness_upper_bound = max(0, horizon - job.due_date)
                earliness_upper_bound = max(
                    0, job.due_date - job_completion_lower_bound
                )
                max_tardiness_upper_bound = max(
                    max_tardiness_upper_bound, tardiness_upper_bound
                )

                if objective.total_tardiness or objective.max_tardiness:
                    tardiness = model.NewIntVar(
                        tardiness_lower_bound,
                        max(tardiness_lower_bound, tardiness_upper_bound),
                        f"tardiness_{job_name}",
                    )
                    model.AddMaxEquality(
                        tardiness,
                        [
                            completion - job.due_date,
                            model.NewConstant(0),
                        ],
                    )
                    tardiness_vars.append(tardiness)
                    if heuristic_completion is not None:
                        tardiness_hint = max(
                            0, heuristic_completion - job.due_date
                        )
                        model.AddHint(tardiness, tardiness_hint)
                        per_job_tardiness_hints.append(tardiness_hint)
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
                    if heuristic_completion is not None:
                        model.AddHint(
                            tardy,
                            int(heuristic_completion > job.due_date),
                        )
                    terms.append(objective.num_tardy_jobs * tardy)
                if objective.total_earliness:
                    earliness = model.NewIntVar(
                        0,
                        max(0, earliness_upper_bound),
                        f"earliness_{job_name}",
                    )
                    model.AddMaxEquality(
                        earliness,
                        [
                            job.due_date - completion,
                            model.NewConstant(0),
                        ],
                    )
                    if heuristic_completion is not None:
                        model.AddHint(
                            earliness,
                            max(0, job.due_date - heuristic_completion),
                        )
                    terms.append(objective.total_earliness * earliness)

        if objective.max_tardiness:
            max_tardiness = model.NewIntVar(
                0,
                max(0, max_tardiness_upper_bound),
                "max_tardiness",
            )
            if tardiness_vars:
                model.AddMaxEquality(max_tardiness, tardiness_vars)
                if per_job_tardiness_hints:
                    model.AddHint(max_tardiness, max(per_job_tardiness_hints))
            else:
                model.Add(max_tardiness == 0)
            terms.append(objective.max_tardiness * max_tardiness)

        return sum(terms)
