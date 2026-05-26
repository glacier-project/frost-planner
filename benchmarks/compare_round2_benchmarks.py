# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Print markdown comparison tables for the full round-2 benchmark matrix.

Pairs every CSV under ``benchmarks/results/`` named
``cp_sat_round2_<cell>_<baseline-label>.csv`` with its counterpart
``cp_sat_round2_<cell>_<head-label>.csv`` and renders one markdown table
per cell (one row per profile inside that cell). The cell list is taken
from ``run_round2_benchmarks.build_suites`` so the matrix is defined in a
single place.

Usage::

    uv run python benchmarks/compare_round2_benchmarks.py
        --baseline-label baseline --head-label head
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from compare_results import render_table
from run_round2_benchmarks import RESULTS_DIR, build_suites

if TYPE_CHECKING:
    from pathlib import Path


def csv_path(cell: str, label: str) -> Path:
    """Return the canonical CSV path for one round-2 (cell, label) pair."""
    return RESULTS_DIR / f"cp_sat_round2_{cell}_{label}.csv"


def main() -> None:
    """Render one markdown table per round-2 cell."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--head-label", default="head")
    args = parser.parse_args()

    sections: list[str] = []
    for suite in build_suites():
        baseline_path = csv_path(suite.name, args.baseline_label)
        head_path = csv_path(suite.name, args.head_label)
        if not baseline_path.exists() or not head_path.exists():
            missing = (
                baseline_path.name
                if not baseline_path.exists()
                else head_path.name
            )
            sections.append(
                f"## {suite.name}\n\n(missing CSV: {missing})"
            )
            continue
        sections.append(
            render_table(
                baseline_path=baseline_path,
                new_path=head_path,
                baseline_label=args.baseline_label,
                new_label=args.head_label,
                profiles=list(suite.profiles),
                title=suite.name,
            )
        )
    print("\n\n".join(sections))


if __name__ == "__main__":
    main()
