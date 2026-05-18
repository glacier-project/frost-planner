# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Run the round-2 benchmark matrix for items #20-#32 head-to-head.

Each invocation runs the full standard matrix once and writes a CSV per
cell under ``benchmarks/results/cp_sat_round2_<cell>_<label>.csv``. The
two CSV families (``head`` vs ``baseline``) can then be diffed cell by
cell to measure the cumulative effect of items #20-#32.

Matrix:

* 4 stress profiles (capability_bottleneck, identical_jobs,
  identical_machines, single_task_jobs) crossed with the 5
  ``SCENARIO_OBJECTIVES`` scenarios, 4 s time limit each;
* ``pruning_smlx`` — small/medium/large/xlarge on
  ``fixed_instances_pruning`` at 4 s;
* ``pruning_huge`` — huge tier on the same dir at 8 s (4 s leaves
  too many UNKNOWN runs on the current instance);
* ``breakable_smlx`` — small/medium/large/xlarge on
  ``fixed_instances_breakable`` at 4 s with the
  ``--breakable-task-ratio 0.5 / minproc 8`` flag combo that matches
  the persisted instance filenames;
* ``breakable_huge`` — huge tier with
  ``--breakable-task-ratio 0.3 / minproc 10`` (the flags the persisted
  huge breakable file was generated with) at 12 s (4 s is below the
  feasible-search threshold per item #19's handoff entry).

Usage (one line; line breaks are illustrative only)::

    uv run --group ortools python benchmarks/run_round2_benchmarks.py
        --label head

    uv run --group ortools python benchmarks/run_round2_benchmarks.py
        --label baseline --only pruning_smlx pruning_huge

Add a new ``Suite`` entry below if a future round-N benchmark needs a
different cell — do not paste shell loops into the conversation.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
BENCHMARK_SCRIPT = REPO_ROOT / "benchmarks" / "benchmark_solvers.py"

STRESS_PROFILES = [
    "stress_capability_bottleneck",
    "stress_identical_jobs",
    "stress_identical_machines",
    "stress_single_task_jobs",
]
SCENARIOS = [
    "pure-makespan",
    "tardiness-mix",
    "due-date-deviation",
    "max-tardiness-focus",
    "flow-time-mix",
]

SHARED_ARGS = [
    "--instances-per-profile", "1",
    "--repeats", "10",
    "--solvers", "cp_sat",
    "--cp-sat-workers", "16",
    "--skip-oracle",
    "--cp-sat-travel-model", "pairwise",
    "--enable-cp-sat-dependency-bounds",
]


@dataclass(frozen=True)
class Suite:
    """One benchmark cell: a labelled CSV plus its CLI args."""

    name: str
    profiles: tuple[str, ...]
    time_limit_seconds: int
    instances_subdir: str
    extra_args: tuple[str, ...] = field(default_factory=tuple)


def build_suites() -> list[Suite]:
    """Return the round-2 suite list in execution order."""
    suites: list[Suite] = []
    for scenario in SCENARIOS:
        suites.append(
            Suite(
                name=f"stress_{scenario}",
                profiles=tuple(STRESS_PROFILES),
                time_limit_seconds=4,
                instances_subdir="fixed_instances_stress",
                extra_args=("--scenario", scenario),
            )
        )
    suites.extend(
        [
            Suite(
                name="pruning_smlx",
                profiles=("small", "medium", "large", "xlarge"),
                time_limit_seconds=4,
                instances_subdir="fixed_instances_pruning",
            ),
            Suite(
                name="pruning_huge",
                profiles=("huge",),
                time_limit_seconds=8,
                instances_subdir="fixed_instances_pruning",
            ),
            Suite(
                name="breakable_smlx",
                profiles=("small", "medium", "large", "xlarge"),
                time_limit_seconds=4,
                instances_subdir="fixed_instances_breakable",
                extra_args=(
                    "--breakable-task-ratio", "0.5",
                    "--breakable-task-min-processing-time", "8",
                    "--machine-break-start", "40",
                    "--machine-break-duration", "20",
                    "--machine-break-repeat", "120",
                    "--machine-window-horizon", "2500",
                ),
            ),
            Suite(
                name="breakable_huge",
                profiles=("huge",),
                time_limit_seconds=12,
                instances_subdir="fixed_instances_breakable",
                extra_args=(
                    "--breakable-task-ratio", "0.3",
                    "--breakable-task-min-processing-time", "10",
                    "--machine-break-start", "400",
                    "--machine-break-duration", "10",
                    "--machine-break-repeat", "600",
                    "--machine-window-horizon", "12000",
                ),
            ),
        ]
    )
    return suites


def run_suite(suite: Suite, label: str) -> Path:
    """Run one benchmark cell, returning the produced CSV path."""
    output = RESULTS_DIR / f"cp_sat_round2_{suite.name}_{label}.csv"
    command = [
        sys.executable,
        str(BENCHMARK_SCRIPT),
        "--profiles", *suite.profiles,
        *SHARED_ARGS,
        "--cp-sat-time-limit", str(suite.time_limit_seconds),
        "--instances-dir", str(RESULTS_DIR / suite.instances_subdir),
        *suite.extra_args,
        "--output", str(output),
    ]
    print(f"=== {suite.name} ({label}, {suite.time_limit_seconds}s) ===")
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"benchmark cell {suite.name} failed (exit {result.returncode})"
        )
    return output


def main() -> None:
    """CLI entry point."""
    suites = build_suites()
    suite_names = [suite.name for suite in suites]
    parser = argparse.ArgumentParser(
        description=(
            "Run the round-2 benchmark matrix and write per-cell CSVs "
            "labelled with --label (e.g. 'head' or 'baseline')."
        )
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Suffix used in every output CSV name (e.g. head, baseline).",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=suite_names,
        default=None,
        help="Optionally restrict execution to a subset of suites.",
    )
    args = parser.parse_args()

    selected_names = set(args.only) if args.only else set(suite_names)
    for suite in suites:
        if suite.name in selected_names:
            run_suite(suite, args.label)


if __name__ == "__main__":
    main()
