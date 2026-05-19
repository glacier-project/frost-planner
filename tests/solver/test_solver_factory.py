# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys
from collections.abc import Callable

import pytest

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.objective import ObjectiveWeights
from frost_planner.solver.cp_sat_solver import CpSatOptions, CpSatSolver
from frost_planner.solver.dummy_solver import DummySolver
from frost_planner.solver.factory import (
    CpSatSolverConfiguration,
    DummySolverConfiguration,
    GeneticAlgorithmSolverConfiguration,
    SolverConfiguration,
    StochasticSolverConfiguration,
    create_solver,
)
from frost_planner.solver.genetic_solver import GeneticAlgorithmSolver
from frost_planner.solver.stochastic_solver import StochasticSolver

SolverClass = (
    type[DummySolver]
    | type[StochasticSolver]
    | type[GeneticAlgorithmSolver]
    | type[CpSatSolver]
)


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


def _stochastic_configuration(
    instance: SchedulingInstance,
) -> SolverConfiguration:
    return StochasticSolverConfiguration(instance=instance)


def _genetic_configuration(instance: SchedulingInstance) -> SolverConfiguration:
    return GeneticAlgorithmSolverConfiguration(instance=instance)


def _cp_sat_configuration(instance: SchedulingInstance) -> SolverConfiguration:
    return CpSatSolverConfiguration(instance=instance)


@pytest.mark.parametrize(
    ("configuration", "solver_class"),
    [
        (_dummy_configuration, DummySolver),
        (_stochastic_configuration, StochasticSolver),
        (_genetic_configuration, GeneticAlgorithmSolver),
        (_cp_sat_configuration, CpSatSolver),
    ],
)
def test_create_solver_from_configuration(
    instance: SchedulingInstance,
    configuration: Callable[[SchedulingInstance], SolverConfiguration],
    solver_class: SolverClass,
) -> None:
    sc = configuration(instance)
    sc.horizon = 100
    sc.machine_intervals = {"M1": [(5, sys.maxsize)]}
    sc.objective = ObjectiveWeights(makespan=0, total_flow_time=1)

    solver = create_solver(sc)

    assert isinstance(solver, solver_class)
    assert solver.instance == instance
    assert solver.horizon == 100
    assert solver.initial_machine_intervals == sc.machine_intervals
    assert solver.objective == sc.objective


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


def test_create_cp_sat_solver_with_ad_hoc_parameters(
    instance: SchedulingInstance,
) -> None:
    solver = create_solver(
        CpSatSolverConfiguration(
            instance=instance,
            options=CpSatOptions(
                time_limit_seconds=2.5,
                num_workers=2,
                relative_gap=0.01,
                log_search_progress=True,
                use_travel_table=False,
                travel_model="hybrid",
                hybrid_travel_threshold=4,
                use_dependency_bounds=True,
                use_machine_load_bounds=True,
                prune_infeasible_alternatives=False,
                use_heuristic_hints=False,
            ),
        )
    )

    assert isinstance(solver, CpSatSolver)
    assert solver.options.time_limit_seconds == 2.5
    assert solver.options.num_workers == 2
    assert solver.options.relative_gap == 0.01
    assert solver.options.log_search_progress is True
    assert solver.options.travel_model == "hybrid"
    assert solver.options.uses_travel_table is False
    assert solver.options.hybrid_travel_threshold == 4
    assert solver.options.use_dependency_bounds is True
    assert solver.options.use_machine_load_bounds is True
    assert solver.options.prune_infeasible_alternatives is False
    assert solver.options.use_heuristic_hints is False


def test_create_cp_sat_solver_defaults_to_pairwise_travel(
    instance: SchedulingInstance,
) -> None:
    solver = create_solver(CpSatSolverConfiguration(instance=instance))

    assert isinstance(solver, CpSatSolver)
    assert solver.options.num_workers == 16
    assert solver.options.travel_model == "pairwise"
    assert solver.options.uses_travel_table is False


def test_create_cp_sat_solver_supports_legacy_table_flag(
    instance: SchedulingInstance,
) -> None:
    solver = create_solver(
        CpSatSolverConfiguration(
            instance=instance,
            options=CpSatOptions(use_travel_table=True),
        )
    )

    assert isinstance(solver, CpSatSolver)
    assert solver.options.travel_model == "table"
    assert solver.options.uses_travel_table is True


def test_create_solver_uses_default_specific_parameters_for_base_configuration(
    instance: SchedulingInstance,
) -> None:
    solver = create_solver(StochasticSolverConfiguration(instance=instance))

    assert isinstance(solver, StochasticSolver)
    assert solver.T == 1000
    assert solver.B == 400


def test_create_solver_rejects_unknown_type(
    instance: SchedulingInstance,
) -> None:
    with pytest.raises(ValueError, match="Unsupported solver type"):
        create_solver(
            DummySolverConfiguration(
                instance=instance,
                solver_type="unknown",
            )
        )


def test_solver_configuration_cannot_be_instantiated(
    instance: SchedulingInstance,
) -> None:
    """The abstract base rejects direct construction."""
    with pytest.raises(TypeError, match="abstract"):
        SolverConfiguration(instance=instance)
