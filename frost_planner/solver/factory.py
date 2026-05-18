# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys
from abc import ABC
from dataclasses import dataclass
from enum import StrEnum

from frost_planner.core.base import SchedulingInstance
from frost_planner.core.objective import ObjectiveWeights
from frost_planner.solver.base_solver import BaseSolver
from frost_planner.solver.dummy_solver import DummySolver
from frost_planner.solver.genetic_solver import GeneticAlgorithmSolver
from frost_planner.solver.stochastic_solver import StochasticSolver


class SolverType(StrEnum):
    """Supported solver identifiers."""

    DUMMY = "dummy"
    STOCHASTIC = "stochastic"
    GENETIC = "genetic"
    CP_SAT = "cp_sat"


@dataclass
class SolverConfiguration(ABC):
    """Common configuration for every solver.

    Abstract base: instantiate one of the concrete subclasses (e.g.
    `DummySolverConfiguration`) instead.
    """

    instance: SchedulingInstance
    solver_type: SolverType | str = SolverType.DUMMY
    horizon: int = sys.maxsize
    machine_intervals: dict[str, list[tuple[int, int]]] | None = None
    objective: ObjectiveWeights | None = None

    def __post_init__(self) -> None:
        """Reject direct instantiation of the abstract base class."""
        if type(self) is SolverConfiguration:
            raise TypeError(
                "SolverConfiguration is abstract and cannot be instantiated "
                "directly; use a concrete subclass (DummySolverConfiguration, "
                "StochasticSolverConfiguration, "
                "GeneticAlgorithmSolverConfiguration, "
                "CpSatSolverConfiguration)."
            )


@dataclass
class DummySolverConfiguration(SolverConfiguration):
    """Configuration for the dummy solver."""

    solver_type: SolverType | str = SolverType.DUMMY


@dataclass
class StochasticSolverConfiguration(SolverConfiguration):
    """Configuration for the stochastic solver."""

    solver_type: SolverType | str = SolverType.STOCHASTIC
    T: int = 1000
    B: int = 400
    R: int = 16
    alpha: float = 0.4
    t_idle: int = 10


@dataclass
class GeneticAlgorithmSolverConfiguration(SolverConfiguration):
    """Configuration for the genetic algorithm solver."""

    solver_type: SolverType | str = SolverType.GENETIC
    population_size: int = 100
    generations: int = 500
    mutation_rate: float = 0.01
    crossover_rate: float = 0.9
    elitism_count: int = 5


@dataclass
class CpSatSolverConfiguration(SolverConfiguration):
    """Configuration for the CP-SAT solver."""

    solver_type: SolverType | str = SolverType.CP_SAT
    time_limit_seconds: float | None = None
    num_workers: int | None = 16
    relative_gap: float = 0.0
    log_search_progress: bool = False
    use_travel_table: bool | None = None
    travel_model: str | None = None
    hybrid_travel_threshold: int = 16
    use_dependency_bounds: bool = False
    use_machine_load_bounds: bool = False
    prune_infeasible_alternatives: bool = True
    use_heuristic_hints: bool = True
    random_seed: int | None = None
    max_deterministic_time: float | None = None
    search_branching: str | None = None
    linearization_level: int | None = None
    cp_model_presolve: bool | None = None
    use_search_strategy: bool = False


def create_solver(configuration: SolverConfiguration) -> BaseSolver:
    """Create a solver instance from a solver configuration."""
    try:
        solver_type = SolverType(configuration.solver_type)
    except ValueError as exc:
        supported_types = ", ".join(
            solver_type.value for solver_type in SolverType
        )
        msg = (
            f"Unsupported solver type {configuration.solver_type!r}. "
            f"Supported solver types: {supported_types}."
        )
        raise ValueError(msg) from exc

    if solver_type is SolverType.DUMMY:
        return DummySolver(
            instance=configuration.instance,
            horizon=configuration.horizon,
            machine_intervals=configuration.machine_intervals,
            objective=configuration.objective,
        )

    if solver_type is SolverType.STOCHASTIC:
        assert isinstance(configuration, StochasticSolverConfiguration), (
            "Expected StochasticSolverConfiguration for stochastic solver type"
        )

        return StochasticSolver(
            instance=configuration.instance,
            horizon=configuration.horizon,
            machine_intervals=configuration.machine_intervals,
            objective=configuration.objective,
            T=configuration.T,
            B=configuration.B,
            R=configuration.R,
            alpha=configuration.alpha,
            t_idle=configuration.t_idle,
        )

    if solver_type is SolverType.CP_SAT:
        assert isinstance(configuration, CpSatSolverConfiguration), (
            "Expected CpSatSolverConfiguration for CP-SAT solver type"
        )
        from frost_planner.solver.cp_sat_solver import CpSatSolver

        return CpSatSolver(
            instance=configuration.instance,
            horizon=configuration.horizon,
            machine_intervals=configuration.machine_intervals,
            time_limit_seconds=configuration.time_limit_seconds,
            num_workers=configuration.num_workers,
            relative_gap=configuration.relative_gap,
            log_search_progress=configuration.log_search_progress,
            use_travel_table=configuration.use_travel_table,
            travel_model=configuration.travel_model,
            hybrid_travel_threshold=configuration.hybrid_travel_threshold,
            use_dependency_bounds=configuration.use_dependency_bounds,
            use_machine_load_bounds=configuration.use_machine_load_bounds,
            prune_infeasible_alternatives=(
                configuration.prune_infeasible_alternatives
            ),
            use_heuristic_hints=configuration.use_heuristic_hints,
            objective=configuration.objective,
            random_seed=configuration.random_seed,
            max_deterministic_time=configuration.max_deterministic_time,
            search_branching=configuration.search_branching,
            linearization_level=configuration.linearization_level,
            cp_model_presolve=configuration.cp_model_presolve,
            use_search_strategy=configuration.use_search_strategy,
        )

    assert isinstance(configuration, GeneticAlgorithmSolverConfiguration), (
        "Expected GeneticAlgorithmSolverConfiguration for genetic solver type"
    )
    return GeneticAlgorithmSolver(
        instance=configuration.instance,
        horizon=configuration.horizon,
        machine_intervals=configuration.machine_intervals,
        objective=configuration.objective,
        population_size=configuration.population_size,
        generations=configuration.generations,
        mutation_rate=configuration.mutation_rate,
        crossover_rate=configuration.crossover_rate,
        elitism_count=configuration.elitism_count,
    )
