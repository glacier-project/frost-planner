# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Shared dataclasses and small helpers for the CP-SAT solver package."""

from dataclasses import dataclass
from typing import Any

from frost_planner.core.base import Machine, Task


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
