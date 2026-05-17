# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

from dataclasses import dataclass

from frost_planner.core.base import SchedulingInstance
from frost_planner.core.metrics import (
    calculate_makespan,
    calculate_max_tardiness,
    calculate_num_tardy_jobs,
    calculate_total_earliness,
    calculate_total_job_flow_time,
    calculate_total_tardiness,
)
from frost_planner.core.schedule import Schedule


@dataclass(frozen=True)
class ObjectiveWeights:
    """Weighted objective terms supported by Frost Planner solvers."""

    makespan: int = 1
    total_flow_time: int = 0
    num_tardy_jobs: int = 0
    total_tardiness: int = 0
    total_earliness: int = 0
    max_tardiness: int = 0

    def __post_init__(self) -> None:
        """Validate objective weights."""
        weights = (
            self.makespan,
            self.total_flow_time,
            self.num_tardy_jobs,
            self.total_tardiness,
            self.total_earliness,
            self.max_tardiness,
        )
        if any(weight < 0 for weight in weights):
            raise ValueError("Objective weights must be non-negative.")
        if not any(weight > 0 for weight in weights):
            raise ValueError(
                "At least one objective weight must be greater than zero."
            )

    @property
    def is_pure_makespan(self) -> bool:
        """Return whether the objective is only makespan minimization."""
        return self == ObjectiveWeights()

    @property
    def needs_job_completion(self) -> bool:
        """Return whether any term needs per-job completion variables."""
        return bool(
            self.total_flow_time
            or self.num_tardy_jobs
            or self.total_tardiness
            or self.total_earliness
            or self.max_tardiness
        )

    @property
    def needs_tardiness_var(self) -> bool:
        """Return whether any term needs per-job tardiness variables."""
        return bool(self.total_tardiness or self.max_tardiness)


def calculate_objective_value(
    schedule: Schedule,
    instance: SchedulingInstance,
    objective: ObjectiveWeights,
) -> float:
    """Calculate a weighted objective value for a complete schedule."""
    value = 0.0
    if objective.makespan:
        value += objective.makespan * calculate_makespan(schedule)
    if objective.total_flow_time:
        value += objective.total_flow_time * calculate_total_job_flow_time(
            schedule,
            instance,
        )
    if objective.num_tardy_jobs:
        value += objective.num_tardy_jobs * calculate_num_tardy_jobs(
            schedule,
            instance,
        )
    if objective.total_tardiness:
        value += objective.total_tardiness * calculate_total_tardiness(
            schedule,
            instance,
        )
    if objective.total_earliness:
        value += objective.total_earliness * calculate_total_earliness(
            schedule,
            instance,
        )
    if objective.max_tardiness:
        value += objective.max_tardiness * calculate_max_tardiness(
            schedule,
            instance,
        )
    return value
