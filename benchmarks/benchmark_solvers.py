# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Benchmark Frost Planner solvers on generated scheduling instances.

The benchmark records whether each solver found a valid schedule, how long it
took, the resulting makespan and flow metrics, and whether optimality was
proved or matched against a CP-SAT oracle.
"""

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from frost_planner.core.base import Machine, SchedulingInstance
from frost_planner.core.metrics import (
    calculate_makespan,
    calculate_num_tardy_jobs,
    calculate_total_flow_time,
)
from frost_planner.core.objective import ObjectiveWeights
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.core.validate import validate_schedule
from frost_planner.generator.instance_generator import (
    InstanceConfiguration,
    InstanceGenerator,
    load_instance_from_json,
    save_instance_to_json,
)
from frost_planner.solver.base_solver import BaseSolver
from frost_planner.solver.cp_sat_solver import CpSatOptions
from frost_planner.solver.factory import (
    CpSatSolverConfiguration,
    DummySolverConfiguration,
    GeneticAlgorithmSolverConfiguration,
    SolverConfiguration,
    StochasticSolverConfiguration,
    create_solver,
)

PROFILES = {
    "tiny": InstanceConfiguration(
        num_jobs=3,
        min_tasks_per_job=2,
        max_tasks_per_job=3,
        num_machine_capabilities=3,
        num_machines=5,
        min_processing_time=2,
        max_processing_time=8,
        min_job_due_date_offset=5,
        max_job_due_date_offset=30,
        min_travel_time=0,
        max_travel_time=3,
    ),
    "small": InstanceConfiguration(
        num_jobs=6,
        min_tasks_per_job=2,
        max_tasks_per_job=4,
        num_machine_capabilities=4,
        num_machines=8,
        min_processing_time=3,
        max_processing_time=12,
        min_job_due_date_offset=10,
        max_job_due_date_offset=50,
        min_travel_time=0,
        max_travel_time=5,
    ),
    "medium": InstanceConfiguration(
        num_jobs=10,
        min_tasks_per_job=3,
        max_tasks_per_job=5,
        num_machine_capabilities=5,
        num_machines=14,
        min_processing_time=5,
        max_processing_time=20,
        min_job_due_date_offset=20,
        max_job_due_date_offset=100,
        min_travel_time=0,
        max_travel_time=8,
    ),
    "large": InstanceConfiguration(
        num_jobs=14,
        min_tasks_per_job=4,
        max_tasks_per_job=6,
        num_machine_capabilities=6,
        num_machines=18,
        min_processing_time=5,
        max_processing_time=25,
        min_job_due_date_offset=30,
        max_job_due_date_offset=130,
        min_task_dependencies=1,
        max_task_dependencies=3,
        min_travel_time=0,
        max_travel_time=10,
    ),
    "xlarge": InstanceConfiguration(
        num_jobs=18,
        min_tasks_per_job=5,
        max_tasks_per_job=7,
        num_machine_capabilities=7,
        num_machines=24,
        min_processing_time=5,
        max_processing_time=30,
        min_job_due_date_offset=40,
        max_job_due_date_offset=180,
        min_task_dependencies=1,
        max_task_dependencies=3,
        min_travel_time=0,
        max_travel_time=12,
    ),
    "huge": InstanceConfiguration(
        num_jobs=30,
        min_tasks_per_job=8,
        max_tasks_per_job=12,
        num_machine_capabilities=8,
        num_machines=32,
        min_processing_time=5,
        max_processing_time=40,
        min_job_due_date_offset=80,
        max_job_due_date_offset=300,
        min_task_dependencies=2,
        max_task_dependencies=4,
        min_travel_time=0,
        max_travel_time=15,
    ),
    # Stress profiles target structural features the random generator does
    # not naturally surface. Fixed instances live under
    # ``benchmarks/results/fixed_instances_stress/`` and are produced by
    # ``benchmarks/generate_stress_instances.py``; the configurations below
    # are fallback shapes used only when the fixed file is missing.
    "stress_capability_bottleneck": InstanceConfiguration(
        num_jobs=20,
        min_tasks_per_job=3,
        max_tasks_per_job=3,
        num_machine_capabilities=2,
        num_machines=10,
        min_processing_time=3,
        max_processing_time=4,
        min_job_due_date_offset=40,
        max_job_due_date_offset=60,
        min_travel_time=2,
        max_travel_time=2,
    ),
    "stress_identical_jobs": InstanceConfiguration(
        num_jobs=12,
        min_tasks_per_job=2,
        max_tasks_per_job=2,
        num_machine_capabilities=2,
        num_machines=4,
        min_processing_time=5,
        max_processing_time=7,
        min_job_due_date_offset=100,
        max_job_due_date_offset=120,
        min_travel_time=3,
        max_travel_time=3,
    ),
    "stress_identical_machines": InstanceConfiguration(
        num_jobs=18,
        min_tasks_per_job=2,
        max_tasks_per_job=2,
        num_machine_capabilities=3,
        num_machines=6,
        min_processing_time=5,
        max_processing_time=6,
        min_job_due_date_offset=60,
        max_job_due_date_offset=80,
        min_travel_time=0,
        max_travel_time=4,
    ),
    "stress_single_task_jobs": InstanceConfiguration(
        num_jobs=10,
        min_tasks_per_job=1,
        max_tasks_per_job=1,
        num_machine_capabilities=3,
        num_machines=5,
        min_processing_time=3,
        max_processing_time=9,
        min_job_due_date_offset=6,
        max_job_due_date_offset=22,
        min_travel_time=2,
        max_travel_time=2,
    ),
}


@dataclass
class BenchmarkResult:
    """One solver run result."""

    profile: str
    instance_index: int
    repeat_index: int
    seed: int
    solver: str
    num_jobs: int
    num_tasks: int
    num_breakable_tasks: int
    num_machines: int
    solution_found: bool
    valid_schedule: bool
    runtime_seconds: float
    makespan: float | None
    total_flow_time: float | None
    num_tardy_jobs: int | None
    solver_status: str
    solver_proved_optimal: bool
    best_bound: float | None
    oracle_status: str
    oracle_runtime_seconds: float | None
    optimal_makespan: float | None
    matches_proven_optimum: bool | None
    gap_to_optimal_percent: float | None
    best_known_makespan: float | None = None
    gap_to_best_known_percent: float | None = None
    error: str | None = None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Benchmark Frost Planner solvers on generated instances."
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=sorted(PROFILES),
        default=["tiny", "small"],
        help="Instance-size profiles to benchmark.",
    )
    parser.add_argument(
        "--instances-per-profile",
        type=int,
        default=3,
        help="Number of generated instances per profile.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of times to run each solver on each generated instance.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Base seed. Instance seed is seed + profile offset + index.",
    )
    parser.add_argument(
        "--instances-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory for benchmark instance JSON files. Existing "
            "files are reused; missing files are generated and saved."
        ),
    )
    parser.add_argument(
        "--solvers",
        nargs="+",
        choices=["dummy", "stochastic", "genetic", "cp_sat", "pyjobshop"],
        default=["dummy", "stochastic", "genetic", "cp_sat"],
        help="Solvers to run.",
    )
    parser.add_argument(
        "--cp-sat-time-limit",
        type=float,
        default=5.0,
        help="Time limit in seconds for benchmark CP-SAT runs.",
    )
    parser.add_argument(
        "--oracle-time-limit",
        type=float,
        default=30.0,
        help="Time limit in seconds for the CP-SAT optimality oracle.",
    )
    parser.add_argument(
        "--skip-oracle",
        action="store_true",
        help="Skip the separate CP-SAT oracle run.",
    )
    parser.add_argument(
        "--cp-sat-workers",
        type=int,
        default=16,
        help="Number of CP-SAT workers.",
    )
    parser.add_argument(
        "--pyjobshop-time-limit",
        type=float,
        default=None,
        help=(
            "Time limit in seconds for PyJobShop runs. Defaults to "
            "--cp-sat-time-limit."
        ),
    )
    parser.add_argument(
        "--pyjobshop-workers",
        type=int,
        default=None,
        help=(
            "Number of PyJobShop OR-Tools workers. Defaults to "
            "--cp-sat-workers."
        ),
    )
    parser.add_argument(
        "--cp-sat-travel-model",
        choices=["table", "pairwise", "hybrid"],
        default="pairwise",
        help="Travel-time formulation to use for CP-SAT.",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIO_OBJECTIVES),
        default=None,
        help=(
            "Named feature-mix scenario that overrides --objective-* "
            "weights. Pairs with size profiles to form a benchmark matrix."
        ),
    )
    parser.add_argument(
        "--objective-makespan-weight",
        type=int,
        default=1,
        help="Weight for makespan minimization.",
    )
    parser.add_argument(
        "--objective-total-flow-time-weight",
        type=int,
        default=0,
        help="Weight for total job flow-time minimization.",
    )
    parser.add_argument(
        "--objective-num-tardy-jobs-weight",
        type=int,
        default=0,
        help="Weight for minimizing the number of tardy jobs.",
    )
    parser.add_argument(
        "--objective-total-tardiness-weight",
        type=int,
        default=0,
        help="Weight for total tardiness minimization.",
    )
    parser.add_argument(
        "--objective-total-earliness-weight",
        type=int,
        default=0,
        help="Weight for total earliness minimization.",
    )
    parser.add_argument(
        "--objective-max-tardiness-weight",
        type=int,
        default=0,
        help="Weight for maximum tardiness minimization.",
    )
    parser.add_argument(
        "--cp-sat-hybrid-travel-threshold",
        type=int,
        default=16,
        help=(
            "Machine-choice product threshold for CP-SAT hybrid travel. "
            "Edges above this use table constraints."
        ),
    )
    parser.add_argument(
        "--enable-cp-sat-dependency-bounds",
        action="store_true",
        help="Enable CP-SAT dependency-derived start lower bounds.",
    )
    parser.add_argument(
        "--enable-cp-sat-load-bounds",
        action="store_true",
        help="Enable redundant CP-SAT machine-load lower bounds.",
    )
    parser.add_argument(
        "--disable-cp-sat-alternative-pruning",
        action="store_true",
        help="Disable CP-SAT pruning of infeasible task-machine alternatives.",
    )
    parser.add_argument(
        "--disable-cp-sat-heuristic-hints",
        action="store_true",
        help="Disable CP-SAT greedy schedule hints.",
    )
    parser.add_argument(
        "--cp-sat-random-seed",
        type=int,
        default=None,
        help="CP-SAT random seed for reproducibility.",
    )
    parser.add_argument(
        "--cp-sat-max-deterministic-time",
        type=float,
        default=None,
        help=(
            "CP-SAT deterministic-time limit (parallel-safe alternative "
            "to wall-clock --cp-sat-time-limit)."
        ),
    )
    parser.add_argument(
        "--cp-sat-search-branching",
        choices=["automatic", "fixed", "portfolio", "lp", "pseudo_cost"],
        default=None,
        help="Override CP-SAT search branching strategy.",
    )
    parser.add_argument(
        "--cp-sat-linearization-level",
        type=int,
        choices=[0, 1, 2],
        default=None,
        help="Override CP-SAT linearization level (0/1/2).",
    )
    parser.add_argument(
        "--cp-sat-disable-presolve",
        action="store_true",
        help="Disable CP-SAT presolve.",
    )
    parser.add_argument(
        "--enable-cp-sat-search-strategy",
        action="store_true",
        help="Add explicit AddDecisionStrategy on presences then starts.",
    )
    parser.add_argument(
        "--enable-cp-sat-capability-cumulative",
        action="store_true",
        help=(
            "Add a redundant AddCumulative per capability class. Useful "
            "on capability-bottlenecked instances; may slow some "
            "due-date-deviation / non-bottleneck scenarios."
        ),
    )
    parser.add_argument(
        "--enable-cp-sat-repair-hint",
        action="store_true",
        help=(
            "Set solver.parameters.repair_hint = True so CP-SAT can fix "
            "small inconsistencies in the warm-start hint instead of "
            "dropping it whole."
        ),
    )
    parser.add_argument(
        "--cp-sat-optimize-with-lb-tree-search",
        choices=["on", "off"],
        default=None,
        help=(
            "Toggle CP-SAT's optimize_with_lb_tree_search parameter "
            "explicitly (default leaves CP-SAT's choice intact)."
        ),
    )
    parser.add_argument(
        "--cp-sat-use-objective-lb-search",
        choices=["on", "off"],
        default=None,
        help=(
            "Toggle CP-SAT's use_objective_lb_search parameter "
            "explicitly (default leaves CP-SAT's choice intact)."
        ),
    )
    parser.add_argument(
        "--cp-sat-probing-level",
        type=int,
        choices=(0, 1, 2, 3),
        default=None,
        help=(
            "Set CP-SAT's cp_model_probing_level (0=none .. 3=aggressive). "
            "Default leaves CP-SAT's choice intact."
        ),
    )
    parser.add_argument(
        "--cp-sat-symmetry-level",
        type=int,
        choices=(0, 1, 2, 3),
        default=None,
        help=(
            "Set CP-SAT's internal symmetry_level (0..3). Default leaves "
            "CP-SAT's choice intact."
        ),
    )
    parser.add_argument(
        "--cp-sat-disjunctive-encoding",
        choices=("no_overlap", "cumulative"),
        default="no_overlap",
        help=(
            "Choose how machine NoOverlap is encoded: 'no_overlap' uses "
            "AddNoOverlap (default); 'cumulative' uses AddCumulative "
            "with capacity 1."
        ),
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=None,
        help="Optional solver horizon override.",
    )
    parser.add_argument(
        "--machine-break-start",
        type=int,
        default=None,
        help="Optional first machine downtime start time.",
    )
    parser.add_argument(
        "--machine-break-duration",
        type=int,
        default=0,
        help="Machine downtime duration. Set to 0 to disable downtime.",
    )
    parser.add_argument(
        "--machine-break-repeat",
        type=int,
        default=0,
        help=(
            "Repeat machine downtime every N time units. Set to 0 for a "
            "single downtime window."
        ),
    )
    parser.add_argument(
        "--machine-window-horizon",
        type=int,
        default=None,
        help=(
            "Finite machine availability horizon used with downtime windows. "
            "Defaults to a conservative instance-derived value."
        ),
    )
    parser.add_argument(
        "--breakable-task-ratio",
        type=float,
        default=0.0,
        help=(
            "Fraction of generated tasks to mark as breakable. Use with "
            "machine downtime benchmarks to exercise interruption support."
        ),
    )
    parser.add_argument(
        "--machine-processing-time-variation",
        type=float,
        default=0.0,
        help=(
            "Generate per-machine processing-time overrides within this "
            "fraction of each task's base duration."
        ),
    )
    parser.add_argument(
        "--breakable-task-min-processing-time",
        type=int,
        default=0,
        help=(
            "Only generated tasks with processing time at least this value "
            "can be marked breakable."
        ),
    )
    parser.add_argument(
        "--stochastic-iterations",
        type=int,
        default=150,
        help="Stochastic solver T parameter.",
    )
    parser.add_argument(
        "--stochastic-budget",
        type=int,
        default=80,
        help="Stochastic solver B parameter.",
    )
    parser.add_argument(
        "--stochastic-neighbors",
        type=int,
        default=8,
        help="Stochastic solver R parameter.",
    )
    parser.add_argument(
        "--genetic-population",
        type=int,
        default=30,
        help="Genetic solver population size.",
    )
    parser.add_argument(
        "--genetic-generations",
        type=int,
        default=60,
        help="Genetic solver generations.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results/solver_benchmark.csv"),
        help="CSV output path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    return parser.parse_args()


def validate_generation_args(args: argparse.Namespace) -> None:
    """Validate benchmark generation options."""
    if not 0 <= args.breakable_task_ratio <= 1:
        raise ValueError("--breakable-task-ratio must be between 0 and 1.")
    if args.breakable_task_min_processing_time < 0:
        raise ValueError(
            "--breakable-task-min-processing-time must be non-negative."
        )
    if not 0 <= args.machine_processing_time_variation <= 1:
        raise ValueError(
            "--machine-processing-time-variation must be between 0 and 1."
        )
    build_objective(args)


SCENARIO_OBJECTIVES: dict[str, ObjectiveWeights] = {
    "pure-makespan": ObjectiveWeights(
        makespan=1,
    ),
    "tardiness-mix": ObjectiveWeights(
        makespan=1,
        total_tardiness=2,
        num_tardy_jobs=5,
    ),
    "due-date-deviation": ObjectiveWeights(
        makespan=0,
        total_tardiness=1,
        total_earliness=1,
    ),
    "max-tardiness-focus": ObjectiveWeights(
        makespan=1,
        max_tardiness=10,
    ),
    "flow-time-mix": ObjectiveWeights(
        makespan=1,
        total_flow_time=2,
    ),
}


def build_objective(args: argparse.Namespace) -> ObjectiveWeights:
    """Build objective weights from CLI arguments or scenario."""
    scenario = getattr(args, "scenario", None)
    if scenario is not None:
        return SCENARIO_OBJECTIVES[scenario]
    return ObjectiveWeights(
        makespan=args.objective_makespan_weight,
        total_flow_time=args.objective_total_flow_time_weight,
        num_tardy_jobs=args.objective_num_tardy_jobs_weight,
        total_tardiness=args.objective_total_tardiness_weight,
        total_earliness=args.objective_total_earliness_weight,
        max_tardiness=args.objective_max_tardiness_weight,
    )


def count_breakable_tasks(instance: SchedulingInstance) -> int:
    """Return the number of breakable tasks in an instance."""
    return sum(
        int(task.allow_breaks)
        for job in instance.jobs
        for task in job.tasks
    )


def profile_configuration(
    profile_name: str,
    args: argparse.Namespace,
) -> InstanceConfiguration:
    """Return the benchmark profile configuration with CLI overrides."""
    configuration = PROFILES[profile_name]
    if (
        args.breakable_task_ratio <= 0
        and args.machine_processing_time_variation <= 0
    ):
        return configuration
    return replace(
        configuration,
        breakable_task_ratio=args.breakable_task_ratio,
        breakable_task_min_processing_time=(
            args.breakable_task_min_processing_time
        ),
        machine_processing_time_variation=(
            args.machine_processing_time_variation
        ),
    )


def instance_path_for(
    profile_name: str,
    instance_index: int,
    seed: int,
    args: argparse.Namespace,
) -> Path:
    """Return the persisted benchmark instance path."""
    stem = f"{profile_name}_{instance_index}_seed_{seed}"
    if args.breakable_task_ratio > 0:
        ratio_tag = f"{args.breakable_task_ratio:g}".replace(".", "_")
        stem += f"_breakable_{ratio_tag}"
        if args.breakable_task_min_processing_time > 0:
            stem += f"_minproc_{args.breakable_task_min_processing_time}"
    if args.machine_processing_time_variation > 0:
        variation_tag = (
            f"{args.machine_processing_time_variation:g}".replace(".", "_")
        )
        stem += f"_machine_duration_{variation_tag}"
    return args.instances_dir / f"{stem}.json"


def default_machine_window_horizon(instance: SchedulingInstance) -> int:
    """Return a finite horizon for benchmark machine availability windows."""
    total_processing_time = 0
    for job in instance.jobs:
        for task in job.tasks:
            suitable_machines = instance.get_suitable_machines(task)
            total_processing_time += max(
                (
                    task.processing_time_on(machine)
                    for machine in suitable_machines
                ),
                default=task.processing_time,
            )
    num_tasks = sum(len(job.tasks) for job in instance.jobs)
    max_travel_time = max(
        (
            travel_time
            for destinations in instance.travel_times.values()
            for travel_time in destinations.values()
        ),
        default=0,
    )
    num_dependency_edges = sum(
        len(task.dependencies) for job in instance.jobs for task in job.tasks
    )
    return max(
        100,
        (total_processing_time + max_travel_time * num_dependency_edges)
        * max(2, len(instance.machines) // 2)
        + num_tasks,
    )


def build_machine_intervals(
    instance: SchedulingInstance,
    args: argparse.Namespace,
) -> dict[str, list[tuple[int, int]]] | None:
    """Build optional finite machine availability windows for benchmarks."""
    if (
        args.machine_break_start is None
        or args.machine_break_duration <= 0
    ):
        return None
    if args.machine_break_repeat < 0:
        raise ValueError("--machine-break-repeat must be non-negative.")

    horizon = (
        args.machine_window_horizon
        or args.horizon
        or default_machine_window_horizon(instance)
    )
    if horizon <= 0:
        raise ValueError("Machine window horizon must be positive.")

    break_windows = []
    break_start = args.machine_break_start
    while break_start < horizon:
        break_end = min(break_start + args.machine_break_duration, horizon)
        if break_start < break_end:
            break_windows.append((break_start, break_end))
        if args.machine_break_repeat == 0:
            break
        break_start += args.machine_break_repeat

    free_windows = []
    cursor = 0
    for break_start, break_end in break_windows:
        if cursor < break_start:
            free_windows.append((cursor, break_start))
        cursor = max(cursor, break_end)
    if cursor < horizon:
        free_windows.append((cursor, horizon))

    return {machine.id: list(free_windows) for machine in instance.machines}


def build_configuration(
    solver_name: str,
    instance: SchedulingInstance,
    args: argparse.Namespace,
) -> SolverConfiguration:
    """Create a solver configuration for the benchmark."""
    horizon = args.horizon if args.horizon is not None else sys.maxsize
    machine_intervals = build_machine_intervals(instance, args)
    objective = build_objective(args)
    if solver_name == "dummy":
        return DummySolverConfiguration(
            instance=instance,
            horizon=horizon,
            machine_intervals=machine_intervals,
            objective=objective,
        )
    if solver_name == "stochastic":
        return StochasticSolverConfiguration(
            instance=instance,
            horizon=horizon,
            machine_intervals=machine_intervals,
            objective=objective,
            T=args.stochastic_iterations,
            B=args.stochastic_budget,
            R=args.stochastic_neighbors,
        )
    if solver_name == "genetic":
        return GeneticAlgorithmSolverConfiguration(
            instance=instance,
            horizon=horizon,
            machine_intervals=machine_intervals,
            objective=objective,
            population_size=args.genetic_population,
            generations=args.genetic_generations,
        )
    if solver_name == "cp_sat":
        return CpSatSolverConfiguration(
            instance=instance,
            horizon=horizon,
            machine_intervals=machine_intervals,
            objective=objective,
            options=CpSatOptions(
                time_limit_seconds=args.cp_sat_time_limit,
                num_workers=args.cp_sat_workers,
                use_travel_table=args.cp_sat_travel_model == "table",
                travel_model=args.cp_sat_travel_model,
                hybrid_travel_threshold=(
                    args.cp_sat_hybrid_travel_threshold
                ),
                use_dependency_bounds=args.enable_cp_sat_dependency_bounds,
                use_machine_load_bounds=args.enable_cp_sat_load_bounds,
                prune_infeasible_alternatives=(
                    not args.disable_cp_sat_alternative_pruning
                ),
                use_heuristic_hints=(
                    not args.disable_cp_sat_heuristic_hints
                ),
                random_seed=args.cp_sat_random_seed,
                max_deterministic_time=args.cp_sat_max_deterministic_time,
                search_branching=args.cp_sat_search_branching,
                linearization_level=args.cp_sat_linearization_level,
                cp_model_presolve=(
                    False if args.cp_sat_disable_presolve else None
                ),
                use_search_strategy=args.enable_cp_sat_search_strategy,
                use_capability_cumulative=(
                    args.enable_cp_sat_capability_cumulative
                ),
                repair_hint=args.enable_cp_sat_repair_hint,
                optimize_with_lb_tree_search=(
                    None
                    if args.cp_sat_optimize_with_lb_tree_search is None
                    else args.cp_sat_optimize_with_lb_tree_search == "on"
                ),
                use_objective_lb_search=(
                    None
                    if args.cp_sat_use_objective_lb_search is None
                    else args.cp_sat_use_objective_lb_search == "on"
                ),
                cp_model_probing_level=args.cp_sat_probing_level,
                symmetry_level=args.cp_sat_symmetry_level,
                disjunctive_encoding=args.cp_sat_disjunctive_encoding,
            ),
        )
    raise ValueError(f"Unsupported solver {solver_name!r}.")


@dataclass(frozen=True)
class PyJobShopAlternative:
    """One PyJobShop optional task for a Frost task-machine choice."""

    task: Any
    task_index: int
    machine: Machine


def finite_horizon_from_intervals(
    machine_intervals: dict[str, list[tuple[int, int]]] | None,
    args: argparse.Namespace,
) -> int | None:
    """Return a finite horizon implied by benchmark options."""
    if args.horizon is not None:
        return args.horizon
    if machine_intervals is None:
        return None
    return max(
        (
            end
            for intervals in machine_intervals.values()
            for _, end in intervals
        ),
        default=None,
    )


def breaks_from_free_windows(
    free_windows: list[tuple[int, int]],
    horizon: int,
) -> list[tuple[int, int]]:
    """Convert Frost Planner free windows into PyJobShop resource breaks."""
    breaks = []
    cursor = 0
    for start, end in sorted(free_windows):
        clipped_start = max(0, min(start, horizon))
        clipped_end = max(0, min(end, horizon))
        if cursor < clipped_start:
            breaks.append((cursor, clipped_start))
        cursor = max(cursor, clipped_end)
    if cursor < horizon:
        breaks.append((cursor, horizon))
    return breaks


def build_pyjobshop_model(
    instance: SchedulingInstance,
    machine_intervals: dict[str, list[tuple[int, int]]] | None,
    horizon: int | None,
    objective: ObjectiveWeights | None = None,
) -> tuple[Any, dict[str, list[PyJobShopAlternative]]]:
    """Build an equivalent PyJobShop model for benchmark comparison."""
    try:
        from pyjobshop import Model
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PyJobShop benchmark requires the ortools dependency group. "
            "Install it with `uv sync --group ortools`."
        ) from exc

    model = Model()
    objective = objective or ObjectiveWeights()
    model.set_objective(
        weight_makespan=objective.makespan,
        weight_tardy_jobs=objective.num_tardy_jobs,
        weight_total_tardiness=objective.total_tardiness,
        weight_total_flow_time=objective.total_flow_time,
        weight_total_earliness=objective.total_earliness,
        weight_max_tardiness=objective.max_tardiness,
    )
    py_machines = {}
    for machine in instance.machines:
        breaks = []
        if machine_intervals is not None and horizon is not None:
            breaks = breaks_from_free_windows(
                machine_intervals.get(machine.id, []),
                horizon,
            )
        py_machines[machine.id] = model.add_machine(
            breaks=breaks,
            name=machine.id,
        )

    alternatives_by_task: dict[str, list[PyJobShopAlternative]] = {}
    for job in instance.jobs:
        py_job = model.add_job(due_date=job.due_date, name=job.id)
        for task in job.tasks:
            suitable_machines = instance.get_suitable_machines(task)
            if not suitable_machines:
                raise ValueError(
                    f"No suitable machine found for task: {task.id}"
                )

            alternatives = []
            for machine in suitable_machines:
                py_task_kwargs = {
                    "job": py_job,
                    "allow_breaks": task.allow_breaks,
                    "optional": True,
                    "name": f"{task.id}@{machine.id}",
                }
                if horizon is not None:
                    py_task_kwargs["latest_end"] = horizon
                py_task = model.add_task(**py_task_kwargs)
                model.add_mode(
                    py_task,
                    py_machines[machine.id],
                    task.processing_time_on(machine),
                )
                alternatives.append(
                    PyJobShopAlternative(
                        task=py_task,
                        task_index=len(model.tasks) - 1,
                        machine=machine,
                    )
                )

            model.add_select_exactly_one(
                [alternative.task for alternative in alternatives]
            )
            alternatives_by_task[task.id] = alternatives

    task_by_id = {
        task.id: task for job in instance.jobs for task in job.tasks
    }
    for task in task_by_id.values():
        for dependency_id in task.dependencies:
            dependency = task_by_id.get(dependency_id)
            if dependency is None:
                raise ValueError(
                    f"Task {task.id} depends on unknown task {dependency_id}."
                )
            for dependency_alternative in alternatives_by_task[dependency.id]:
                for current_alternative in alternatives_by_task[task.id]:
                    travel_time = instance.get_travel_time(
                        dependency_alternative.machine,
                        current_alternative.machine,
                    )
                    model.add_end_before_start(
                        dependency_alternative.task,
                        current_alternative.task,
                        travel_time,
                    )

    return model, alternatives_by_task


def pyjobshop_schedule_from_result(
    instance: SchedulingInstance,
    alternatives_by_task: dict[str, list[PyJobShopAlternative]],
    result: Any,
) -> Schedule:
    """Convert a PyJobShop result into a Frost Planner schedule."""
    schedule = Schedule(machines=instance.machines)
    for job in instance.jobs:
        for task in job.tasks:
            selected = [
                (alternative, result.best.tasks[alternative.task_index])
                for alternative in alternatives_by_task[task.id]
                if result.best.tasks[alternative.task_index].present
            ]
            if len(selected) != 1:
                raise ValueError(
                    "PyJobShop did not select exactly one alternative for "
                    f"task {task.id}."
                )

            alternative, scheduled_task = selected[0]
            schedule.add_scheduled_task(
                ScheduledTask(
                    start_time=scheduled_task.start,
                    end_time=scheduled_task.end,
                    task=task,
                    machine=alternative.machine,
                    break_time=scheduled_task.breaks,
                )
            )
    return schedule


def pyjobshop_status_name(result: Any) -> str:
    """Return a benchmark-compatible PyJobShop status name."""
    status = result.status
    return getattr(status, "name", str(status).rsplit(".", maxsplit=1)[-1])


def run_pyjobshop_solver(
    instance: SchedulingInstance,
    args: argparse.Namespace,
) -> BenchmarkResult:
    """Run PyJobShop on one instance and collect benchmark metrics."""
    num_tasks = sum(len(job.tasks) for job in instance.jobs)
    num_breakable_tasks = count_breakable_tasks(instance)
    machine_intervals = build_machine_intervals(instance, args)
    horizon = finite_horizon_from_intervals(machine_intervals, args)
    time_limit = (
        args.pyjobshop_time_limit
        if args.pyjobshop_time_limit is not None
        else args.cp_sat_time_limit
    )
    objective = build_objective(args)
    num_workers = (
        args.pyjobshop_workers
        if args.pyjobshop_workers is not None
        else args.cp_sat_workers
    )

    started_at = time.perf_counter()
    try:
        model, alternatives_by_task = build_pyjobshop_model(
            instance,
            machine_intervals,
            horizon,
            objective,
        )
        result = model.solve(
            solver="ortools",
            time_limit=time_limit,
            display=False,
            num_workers=num_workers,
        )
        runtime_seconds = time.perf_counter() - started_at
        solver_status = pyjobshop_status_name(result)
        best_bound = (
            float(result.lower_bound)
            if math.isfinite(result.lower_bound)
            else None
        )

        if not math.isfinite(result.objective):
            return BenchmarkResult(
                profile="",
                instance_index=-1,
                repeat_index=-1,
                seed=-1,
                solver="pyjobshop",
                num_jobs=len(instance.jobs),
                num_tasks=num_tasks,
                num_breakable_tasks=num_breakable_tasks,
                num_machines=len(instance.machines),
                solution_found=False,
                valid_schedule=False,
                runtime_seconds=runtime_seconds,
                makespan=None,
                total_flow_time=None,
                num_tardy_jobs=None,
                solver_status=solver_status,
                solver_proved_optimal=False,
                best_bound=best_bound,
                oracle_status="NOT_RUN",
                oracle_runtime_seconds=None,
                optimal_makespan=None,
                matches_proven_optimum=None,
                gap_to_optimal_percent=None,
            )

        schedule = pyjobshop_schedule_from_result(
            instance,
            alternatives_by_task,
            result,
        )
        valid_schedule = validate_schedule(schedule, instance)
        makespan = calculate_makespan(schedule)
        total_flow_time = calculate_total_flow_time(schedule)
        num_tardy_jobs = calculate_num_tardy_jobs(schedule, instance)
        return BenchmarkResult(
            profile="",
            instance_index=-1,
            repeat_index=-1,
            seed=-1,
            solver="pyjobshop",
            num_jobs=len(instance.jobs),
            num_tasks=num_tasks,
            num_breakable_tasks=num_breakable_tasks,
            num_machines=len(instance.machines),
            solution_found=True,
            valid_schedule=valid_schedule,
            runtime_seconds=runtime_seconds,
            makespan=makespan,
            total_flow_time=total_flow_time,
            num_tardy_jobs=num_tardy_jobs,
            solver_status=solver_status,
            solver_proved_optimal=solver_status == "OPTIMAL",
            best_bound=best_bound,
            oracle_status="NOT_RUN",
            oracle_runtime_seconds=None,
            optimal_makespan=None,
            matches_proven_optimum=None,
            gap_to_optimal_percent=None,
        )
    except Exception as exc:
        runtime_seconds = time.perf_counter() - started_at
        return BenchmarkResult(
            profile="",
            instance_index=-1,
            repeat_index=-1,
            seed=-1,
            solver="pyjobshop",
            num_jobs=len(instance.jobs),
            num_tasks=num_tasks,
            num_breakable_tasks=num_breakable_tasks,
            num_machines=len(instance.machines),
            solution_found=False,
            valid_schedule=False,
            runtime_seconds=runtime_seconds,
            makespan=None,
            total_flow_time=None,
            num_tardy_jobs=None,
            solver_status="ERROR",
            solver_proved_optimal=False,
            best_bound=None,
            oracle_status="NOT_RUN",
            oracle_runtime_seconds=None,
            optimal_makespan=None,
            matches_proven_optimum=None,
            gap_to_optimal_percent=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_solver(
    solver_name: str,
    instance: SchedulingInstance,
    args: argparse.Namespace,
) -> tuple[BenchmarkResult, BaseSolver | None]:
    """Run one solver and collect metrics."""
    if solver_name == "pyjobshop":
        return run_pyjobshop_solver(instance, args), None

    num_tasks = sum(len(job.tasks) for job in instance.jobs)
    num_breakable_tasks = count_breakable_tasks(instance)
    started_at = time.perf_counter()
    solver: BaseSolver | None = None
    try:
        solver = create_solver(build_configuration(solver_name, instance, args))
        schedule = solver.schedule()
        runtime_seconds = time.perf_counter() - started_at
        valid_schedule = validate_schedule(schedule, instance)
        makespan = calculate_makespan(schedule)
        total_flow_time = calculate_total_flow_time(schedule)
        num_tardy_jobs = calculate_num_tardy_jobs(schedule, instance)
        solver_status = str(getattr(solver, "last_status", "FEASIBLE"))
        solver_proved_optimal = solver_status == "OPTIMAL"
        best_bound = getattr(solver, "last_best_bound", None)
        return (
            BenchmarkResult(
                profile="",
                instance_index=-1,
                repeat_index=-1,
                seed=-1,
                solver=solver_name,
                num_jobs=len(instance.jobs),
                num_tasks=num_tasks,
                num_breakable_tasks=num_breakable_tasks,
                num_machines=len(instance.machines),
                solution_found=True,
                valid_schedule=valid_schedule,
                runtime_seconds=runtime_seconds,
                makespan=makespan,
                total_flow_time=total_flow_time,
                num_tardy_jobs=num_tardy_jobs,
                solver_status=solver_status,
                solver_proved_optimal=solver_proved_optimal,
                best_bound=(
                    float(best_bound) if best_bound is not None else None
                ),
                oracle_status="NOT_RUN",
                oracle_runtime_seconds=None,
                optimal_makespan=None,
                matches_proven_optimum=None,
                gap_to_optimal_percent=None,
            ),
            solver,
        )
    except Exception as exc:
        runtime_seconds = time.perf_counter() - started_at
        return (
            BenchmarkResult(
                profile="",
                instance_index=-1,
                repeat_index=-1,
                seed=-1,
                solver=solver_name,
                num_jobs=len(instance.jobs),
                num_tasks=num_tasks,
                num_breakable_tasks=num_breakable_tasks,
                num_machines=len(instance.machines),
                solution_found=False,
                valid_schedule=False,
                runtime_seconds=runtime_seconds,
                makespan=None,
                total_flow_time=None,
                num_tardy_jobs=None,
                solver_status="ERROR",
                solver_proved_optimal=False,
                best_bound=None,
                oracle_status="NOT_RUN",
                oracle_runtime_seconds=None,
                optimal_makespan=None,
                matches_proven_optimum=None,
                gap_to_optimal_percent=None,
                error=f"{type(exc).__name__}: {exc}",
            ),
            solver,
        )


def run_oracle(
    instance: SchedulingInstance,
    args: argparse.Namespace,
) -> tuple[str, float | None, float | None]:
    """Run a longer CP-SAT solve to try proving the optimum."""
    if args.skip_oracle:
        return "SKIPPED", None, None

    oracle_args = argparse.Namespace(**vars(args))
    oracle_args.cp_sat_time_limit = args.oracle_time_limit
    result, _ = run_solver("cp_sat", instance, oracle_args)
    if result.solution_found and result.solver_status == "OPTIMAL":
        return (
            result.solver_status,
            result.runtime_seconds,
            result.makespan,
        )
    return result.solver_status, result.runtime_seconds, None


def percent_gap(value: float, reference: float) -> float:
    """Return percent gap from a positive reference value."""
    if reference == 0:
        return 0.0 if value == 0 else math.inf
    return ((value - reference) / reference) * 100


def annotate_optimality(
    results: list[BenchmarkResult],
    oracle_status: str,
    oracle_runtime_seconds: float | None,
    optimal_makespan: float | None,
) -> None:
    """Fill oracle and best-known fields after all solver runs."""
    feasible_makespans = [
        result.makespan
        for result in results
        if result.solution_found and result.valid_schedule
        and result.makespan is not None
    ]
    best_known_makespan = (
        min(feasible_makespans) if feasible_makespans else None
    )

    for result in results:
        result.oracle_status = oracle_status
        result.oracle_runtime_seconds = oracle_runtime_seconds
        result.optimal_makespan = optimal_makespan
        result.best_known_makespan = best_known_makespan

        if result.makespan is None:
            continue

        if optimal_makespan is not None:
            result.matches_proven_optimum = result.makespan == optimal_makespan
            result.gap_to_optimal_percent = percent_gap(
                result.makespan,
                optimal_makespan,
            )
        if best_known_makespan is not None:
            result.gap_to_best_known_percent = percent_gap(
                result.makespan,
                best_known_makespan,
            )


def generate_instance(
    profile_name: str,
    profile_index: int,
    instance_index: int,
    args: argparse.Namespace,
) -> tuple[SchedulingInstance, int]:
    """Generate one benchmark instance."""
    seed = args.seed + profile_index * 10_000 + instance_index
    if args.instances_dir is not None:
        args.instances_dir.mkdir(parents=True, exist_ok=True)
        instance_path = instance_path_for(
            profile_name,
            instance_index,
            seed,
            args,
        )
        if instance_path.exists():
            return load_instance_from_json(str(instance_path)), seed

    generator = InstanceGenerator(seed=seed)
    instance = generator.create_instance(
        profile_configuration(profile_name, args)
    )
    if args.instances_dir is not None:
        save_instance_to_json(instance, str(instance_path))
    return instance, seed


def write_csv(results: list[BenchmarkResult], output_path: Path) -> None:
    """Write benchmark results to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(result) for result in results]
    if not rows:
        return

    with output_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(results: list[BenchmarkResult], output_path: Path) -> None:
    """Write benchmark results to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as json_file:
        json.dump([asdict(result) for result in results], json_file, indent=2)


def print_summary(results: list[BenchmarkResult]) -> None:
    """Print a compact benchmark summary."""
    print(
        "profile instance repeat solver breakable status valid runtime_s "
        "makespan solver_opt oracle_status oracle_opt gap_best_%"
    )
    for result in results:
        print(
            f"{result.profile:7} "
            f"{result.instance_index:8} "
            f"{result.repeat_index:6} "
            f"{result.solver:10} "
            f"{result.num_breakable_tasks:9} "
            f"{result.solver_status:10} "
            f"{result.valid_schedule!s:5} "
            f"{result.runtime_seconds:9.4f} "
            f"{result.makespan!s:8} "
            f"{result.solver_proved_optimal!s:10} "
            f"{result.oracle_status:12} "
            f"{result.optimal_makespan!s:10} "
            f"{result.gap_to_best_known_percent!s}"
        )


def main() -> None:
    """Run the benchmark suite."""
    args = parse_args()
    validate_generation_args(args)
    results: list[BenchmarkResult] = []

    for profile_index, profile_name in enumerate(args.profiles):
        for instance_index in range(args.instances_per_profile):
            instance, seed = generate_instance(
                profile_name,
                profile_index,
                instance_index,
                args,
            )
            oracle_status, oracle_runtime, optimal_makespan = run_oracle(
                instance,
                args,
            )
            instance_results: list[BenchmarkResult] = []

            for solver_name in args.solvers:
                for repeat_index in range(args.repeats):
                    result, _ = run_solver(solver_name, instance, args)
                    result.profile = profile_name
                    result.instance_index = instance_index
                    result.repeat_index = repeat_index
                    result.seed = seed
                    instance_results.append(result)

            annotate_optimality(
                instance_results,
                oracle_status,
                oracle_runtime,
                optimal_makespan,
            )
            results.extend(instance_results)

    write_csv(results, args.output)
    if args.json_output is not None:
        write_json(results, args.json_output)
    print_summary(results)
    print(f"\nWrote CSV results to {args.output}")
    if args.json_output is not None:
        print(f"Wrote JSON results to {args.json_output}")


if __name__ == "__main__":
    main()
