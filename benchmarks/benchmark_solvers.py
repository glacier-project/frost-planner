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
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from frost_planner.core.base import SchedulingInstance
from frost_planner.core.metrics import (
    calculate_makespan,
    calculate_num_tardy_jobs,
    calculate_total_flow_time,
)
from frost_planner.core.validate import validate_schedule
from frost_planner.generator.instance_generator import (
    InstanceConfiguration,
    InstanceGenerator,
)
from frost_planner.solver.base_solver import BaseSolver
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
}


@dataclass
class BenchmarkResult:
    """One solver run result."""

    profile: str
    instance_index: int
    seed: int
    solver: str
    num_jobs: int
    num_tasks: int
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
        "--seed",
        type=int,
        default=0,
        help="Base seed. Instance seed is seed + profile offset + index.",
    )
    parser.add_argument(
        "--solvers",
        nargs="+",
        choices=["dummy", "stochastic", "genetic", "cp_sat"],
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
        default=8,
        help="Number of CP-SAT workers.",
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


def build_configuration(
    solver_name: str,
    instance: SchedulingInstance,
    args: argparse.Namespace,
) -> SolverConfiguration:
    """Create a solver configuration for the benchmark."""
    if solver_name == "dummy":
        return DummySolverConfiguration(instance=instance)
    if solver_name == "stochastic":
        return StochasticSolverConfiguration(
            instance=instance,
            T=args.stochastic_iterations,
            B=args.stochastic_budget,
            R=args.stochastic_neighbors,
        )
    if solver_name == "genetic":
        return GeneticAlgorithmSolverConfiguration(
            instance=instance,
            population_size=args.genetic_population,
            generations=args.genetic_generations,
        )
    if solver_name == "cp_sat":
        return CpSatSolverConfiguration(
            instance=instance,
            time_limit_seconds=args.cp_sat_time_limit,
            num_workers=args.cp_sat_workers,
        )
    raise ValueError(f"Unsupported solver {solver_name!r}.")


def run_solver(
    solver_name: str,
    instance: SchedulingInstance,
    args: argparse.Namespace,
) -> tuple[BenchmarkResult, BaseSolver | None]:
    """Run one solver and collect metrics."""
    num_tasks = sum(len(job.tasks) for job in instance.jobs)
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
                seed=-1,
                solver=solver_name,
                num_jobs=len(instance.jobs),
                num_tasks=num_tasks,
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
                seed=-1,
                solver=solver_name,
                num_jobs=len(instance.jobs),
                num_tasks=num_tasks,
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
    generator = InstanceGenerator(seed=seed)
    return generator.create_instance(PROFILES[profile_name]), seed


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
        "profile instance solver status valid runtime_s makespan "
        "solver_opt oracle_status oracle_opt gap_best_%"
    )
    for result in results:
        print(
            f"{result.profile:7} "
            f"{result.instance_index:8} "
            f"{result.solver:10} "
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
                result, _ = run_solver(solver_name, instance, args)
                result.profile = profile_name
                result.instance_index = instance_index
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
