import sys
from dataclasses import dataclass
from enum import Enum

from frost_planner.core.base import SchedulingInstance
from frost_planner.solver.base_solver import BaseSolver
from frost_planner.solver.dummy_solver import DummySolver
from frost_planner.solver.genetic_solver import GeneticAlgorithmSolver
from frost_planner.solver.stochastic_solver import StochasticSolver


class SolverType(str, Enum):
    """Supported solver identifiers."""

    DUMMY = "dummy"
    STOCHASTIC = "stochastic"
    GENETIC = "genetic"


@dataclass
class SolverConfiguration:
    """Common configuration for every solver."""

    instance: SchedulingInstance
    solver_type: SolverType | str = SolverType.DUMMY
    horizon: int = sys.maxsize
    machine_intervals: dict[str, list[tuple[int, int]]] | None = None


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


def create_solver(configuration: SolverConfiguration) -> BaseSolver:
    """Create a solver instance from a solver configuration."""
    try:
        solver_type = SolverType(configuration.solver_type)
    except ValueError as exc:
        supported_types = ", ".join(solver_type.value for solver_type in SolverType)
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
        )

    if solver_type is SolverType.STOCHASTIC:
        assert isinstance(
            configuration, StochasticSolverConfiguration
        ), "Expected StochasticSolverConfiguration for stochastic solver type"

        return StochasticSolver(
            instance=configuration.instance,
            horizon=configuration.horizon,
            machine_intervals=configuration.machine_intervals,
            T=configuration.T,
            B=configuration.B,
            R=configuration.R,
            alpha=configuration.alpha,
            t_idle=configuration.t_idle,
        )

    assert isinstance(
        configuration, GeneticAlgorithmSolverConfiguration
    ), "Expected GeneticAlgorithmSolverConfiguration for genetic solver type"
    return GeneticAlgorithmSolver(
        instance=configuration.instance,
        horizon=configuration.horizon,
        machine_intervals=configuration.machine_intervals,
        population_size=configuration.population_size,
        generations=configuration.generations,
        mutation_rate=configuration.mutation_rate,
        crossover_rate=configuration.crossover_rate,
        elitism_count=configuration.elitism_count,
    )
