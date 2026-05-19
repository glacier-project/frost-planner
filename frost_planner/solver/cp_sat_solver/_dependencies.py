# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Dependency-edge constraints for the CP-SAT model.

This mixin owns the travel-time encoding for each (dependency → task)
edge: pairwise reified constraints, table-based AddAllowedAssignments,
or a single direct constraint when travel is invariant. It also
contains the helper that decides which tasks need an extra
machine-index variable for the table formulation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from frost_planner.solver.cp_sat_solver._types import (
    _safe_name,
    _TaskVariables,
)

if TYPE_CHECKING:
    from frost_planner.core.base import Machine, SchedulingInstance, Task
    from frost_planner.solver.cp_sat_solver._types import CpSatOptions
    from frost_planner.solver.instance_analysis import InstanceAnalysis


class _DependenciesMixin:
    """Mixin: dependency-edge constraints + travel-time encodings."""

    if TYPE_CHECKING:
        instance: SchedulingInstance
        analysis: InstanceAnalysis
        options: CpSatOptions

    def _table_machine_task_ids(
        self,
        tasks: list[Task],
        feasible_machines_by_task: dict[str, list[Machine]],
    ) -> set[str]:
        """Return tasks that need machine-index variables for table edges."""
        if self.options.travel_model not in {"table", "hybrid"}:
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

                use_table = self.options.travel_model == "table"
                if self.options.travel_model == "hybrid":
                    min_travel = min(travel_times)
                    extra_pair_count = sum(
                        1
                        for travel_time in travel_times
                        if travel_time > min_travel
                    )
                    use_table = (
                        extra_pair_count
                        > self.options.hybrid_travel_threshold
                    )
                if use_table:
                    task_ids.add(dependency_id)
                    task_ids.add(task.id)

        return task_ids

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

                use_table = self.options.travel_model == "table"
                if self.options.travel_model == "hybrid":
                    extra_pair_count = sum(
                        1
                        for travel_time in travel_times
                        if travel_time > min_travel_time
                    )
                    use_table = (
                        extra_pair_count
                        > self.options.hybrid_travel_threshold
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
