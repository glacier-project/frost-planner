import sys
from collections.abc import Callable

import pytest

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.solver.dummy_solver import DummySolver
from frost_planner.solver.factory import (
    DummySolverConfiguration,
    GeneticAlgorithmSolverConfiguration,
    SolverConfiguration,
    SolverType,
    StochasticSolverConfiguration,
    create_solver,
)
from frost_planner.solver.genetic_solver import GeneticAlgorithmSolver
from frost_planner.solver.stochastic_solver import StochasticSolver


SolverClass = type[DummySolver] | type[StochasticSolver] | type[GeneticAlgorithmSolver]


@pytest.fixture
def instance() -> SchedulingInstance:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["cutting"],
    )
    job = Job(id="J1", name="Job 1", tasks=[task])
    machine = Machine(id="M1", name="Machine 1", capabilities=["cutting"])
    return SchedulingInstance(jobs=[job], machines=[machine])


def _dummy_configuration(instance: SchedulingInstance) -> SolverConfiguration:
    return DummySolverConfiguration(instance=instance)


def _stochastic_configuration(instance: SchedulingInstance) -> SolverConfiguration:
    return StochasticSolverConfiguration(instance=instance)


def _genetic_configuration(instance: SchedulingInstance) -> SolverConfiguration:
    return GeneticAlgorithmSolverConfiguration(instance=instance)


def _base_configuration(instance: SchedulingInstance) -> SolverConfiguration:
    return SolverConfiguration(
        instance=instance,
        solver_type="dummy",
    )


@pytest.mark.parametrize(
    ("configuration", "solver_class"),
    [
        (_dummy_configuration, DummySolver),
        (_stochastic_configuration, StochasticSolver),
        (_genetic_configuration, GeneticAlgorithmSolver),
        (_base_configuration, DummySolver),
    ],
)
def test_create_solver_from_configuration(
    instance: SchedulingInstance,
    configuration: Callable[[SchedulingInstance], SolverConfiguration],
    solver_class: SolverClass,
) -> None:
    solver_configuration = configuration(instance)
    solver_configuration.horizon = 100
    solver_configuration.machine_intervals = {"M1": [(5, sys.maxsize)]}

    solver = create_solver(solver_configuration)

    assert isinstance(solver, solver_class)
    assert solver.instance == instance
    assert solver.horizon == 100
    assert solver.initial_machine_intervals == solver_configuration.machine_intervals


def test_create_stochastic_solver_with_ad_hoc_parameters(
    instance: SchedulingInstance,
) -> None:
    solver = create_solver(
        StochasticSolverConfiguration(
            instance=instance,
            T=20,
            B=12,
            R=3,
            alpha=0.25,
            t_idle=4,
        )
    )

    assert isinstance(solver, StochasticSolver)
    assert solver.T == 20
    assert solver.B == 12
    assert solver.R == 3
    assert solver.alpha == 0.25
    assert solver.t_idle == 4


def test_create_genetic_solver_with_ad_hoc_parameters(
    instance: SchedulingInstance,
) -> None:
    solver = create_solver(
        GeneticAlgorithmSolverConfiguration(
            instance=instance,
            population_size=8,
            generations=10,
            mutation_rate=0.2,
            crossover_rate=0.7,
            elitism_count=2,
        )
    )

    assert isinstance(solver, GeneticAlgorithmSolver)
    assert solver.population_size == 8
    assert solver.generations == 10
    assert solver.mutation_rate == 0.2
    assert solver.crossover_rate == 0.7
    assert solver.elitism_count == 2


def test_create_solver_uses_default_specific_parameters_for_base_configuration(
    instance: SchedulingInstance,
) -> None:
    solver = create_solver(
        SolverConfiguration(
            instance=instance,
            solver_type=SolverType.STOCHASTIC,
        )
    )

    assert isinstance(solver, StochasticSolver)
    assert solver.T == 1000
    assert solver.B == 400


def test_create_solver_rejects_unknown_type(
    instance: SchedulingInstance,
) -> None:
    with pytest.raises(ValueError, match="Unsupported solver type"):
        create_solver(
            SolverConfiguration(
                instance=instance,
                solver_type="unknown",
            )
        )
