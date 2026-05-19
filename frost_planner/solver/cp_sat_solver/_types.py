# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Shared dataclasses and small helpers for the CP-SAT solver package."""

from dataclasses import dataclass
from typing import Any, Literal

from frost_planner.core.base import Machine, Task

TravelModel = Literal["table", "pairwise", "hybrid"]
DisjunctiveEncoding = Literal["no_overlap", "cumulative"]
SearchBranching = Literal[
    "automatic", "fixed", "portfolio", "lp", "pseudo_cost"
]
LinearizationLevel = Literal[0, 1, 2]
ProbingLevel = Literal[0, 1, 2, 3]
SymmetryLevel = Literal[0, 1, 2, 3]

TRAVEL_MODELS: tuple[TravelModel, ...] = ("table", "pairwise", "hybrid")
DISJUNCTIVE_ENCODINGS: tuple[DisjunctiveEncoding, ...] = (
    "no_overlap",
    "cumulative",
)
SEARCH_BRANCHINGS: tuple[SearchBranching, ...] = (
    "automatic",
    "fixed",
    "portfolio",
    "lp",
    "pseudo_cost",
)


@dataclass
class CpSatOptions:
    """Tunable knobs for the CP-SAT solver.

    All CP-SAT-specific configuration goes here; the solver constructor
    keeps only the four problem-shape arguments (instance, horizon,
    machine_intervals, objective). The factory's
    ``CpSatSolverConfiguration`` wraps this together with the problem
    shape for dispatch.
    """

    # Search budget / resources.
    time_limit_seconds: float | None = None
    num_workers: int | None = 16
    relative_gap: float = 0.0
    log_search_progress: bool = False
    random_seed: int | None = None
    max_deterministic_time: float | None = None

    # Travel-time formulation.
    travel_model: TravelModel = "pairwise"
    hybrid_travel_threshold: int = 16

    # Bounds / pruning toggles.
    use_dependency_bounds: bool = False
    use_machine_load_bounds: bool = False
    prune_infeasible_alternatives: bool = True
    use_heuristic_hints: bool = True

    # Encoding choices.
    disjunctive_encoding: DisjunctiveEncoding = "no_overlap"
    use_capability_cumulative: bool = False
    use_search_strategy: bool = False
    repair_hint: bool = False

    # CP-SAT solver-parameter knobs.
    search_branching: SearchBranching | None = None
    linearization_level: LinearizationLevel | None = None
    cp_model_presolve: bool | None = None
    optimize_with_lb_tree_search: bool | None = None
    use_objective_lb_search: bool | None = None
    cp_model_probing_level: ProbingLevel | None = None
    symmetry_level: SymmetryLevel | None = None

    def __post_init__(self) -> None:
        """Validate enum-like fields once at construction."""
        if self.num_workers is not None and self.num_workers < 1:
            raise ValueError("num_workers must be positive.")
        if self.relative_gap < 0:
            raise ValueError("relative_gap must be non-negative.")
        if self.hybrid_travel_threshold < 1:
            raise ValueError("hybrid_travel_threshold must be positive.")
        if self.travel_model not in TRAVEL_MODELS:
            raise ValueError(
                f"travel_model must be one of {list(TRAVEL_MODELS)}."
            )
        if (
            self.cp_model_probing_level is not None
            and self.cp_model_probing_level not in (0, 1, 2, 3)
        ):
            raise ValueError(
                "cp_model_probing_level must be 0, 1, 2, or 3."
            )
        if (
            self.symmetry_level is not None
            and self.symmetry_level not in (0, 1, 2, 3)
        ):
            raise ValueError("symmetry_level must be 0, 1, 2, or 3.")
        if self.disjunctive_encoding not in DISJUNCTIVE_ENCODINGS:
            raise ValueError(
                "disjunctive_encoding must be one of "
                f"{list(DISJUNCTIVE_ENCODINGS)}."
            )
        if (
            self.linearization_level is not None
            and self.linearization_level not in (0, 1, 2)
        ):
            raise ValueError("linearization_level must be 0, 1, or 2.")
        if (
            self.search_branching is not None
            and self.search_branching not in SEARCH_BRANCHINGS
        ):
            raise ValueError(
                "search_branching must be one of "
                f"{list(SEARCH_BRANCHINGS)}."
            )

    @property
    def uses_travel_table(self) -> bool:
        """Whether the chosen travel model is the table encoding."""
        return self.travel_model == "table"


@dataclass
class _AlternativeVariables:
    """Variables for one task-machine assignment alternative.

    ``presence`` is None when the alternative is the only feasible
    option and is modeled as a mandatory interval instead of an
    optional one.
    """

    machine: Machine
    processing_time: int
    presence: Any | None
    interval: Any
    break_time: Any


@dataclass
class _TaskVariables:
    """Variables for one task in the CP-SAT model."""

    task: Task
    start: Any
    end: Any
    machine: Any | None
    alternatives: dict[str, _AlternativeVariables]
    locked_machine: Machine | None = None


def _load_cp_model() -> Any:
    """Load OR-Tools lazily so default installs do not require it."""
    try:
        from ortools.sat.python import cp_model
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "CpSatSolver requires the ortools dependency group. Install "
            "it with `uv sync --group ortools`."
        ) from exc
    return cp_model


def _safe_name(value: str) -> str:
    """Return a CP-SAT variable-name-safe version of a user identifier."""
    return "".join(char if char.isalnum() else "_" for char in value)
