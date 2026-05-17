# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Print a markdown comparison table between two benchmark CSV runs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import median


def summarize(path: Path, profile: str) -> dict[str, object] | None:
    """Return median runtime, best/median makespan, and optimal count."""
    rows = [
        row
        for row in csv.DictReader(path.open())
        if row["profile"] == profile
    ]
    if not rows:
        return None
    runtimes = sorted(float(row["runtime_seconds"]) for row in rows)
    makespans = sorted(
        float(row["makespan"]) for row in rows if row["makespan"]
    )
    optimal = sum(
        1 for row in rows if row["solver_proved_optimal"] == "True"
    )
    return {
        "n": len(rows),
        "med_rt": median(runtimes),
        "best": min(makespans) if makespans else None,
        "med_ms": median(makespans) if makespans else None,
        "max_ms": max(makespans) if makespans else None,
        "optimal": optimal,
    }


def _format_makespan(stats: dict[str, object]) -> str:
    """Return a 'best/median' makespan string for a stats dict."""
    best = stats["best"]
    med = stats["med_ms"]
    if best is None or med is None:
        return "-"
    return f"{best:.0f}/{med:.0f}"


def render_table(
    baseline_path: Path,
    new_path: Path,
    baseline_label: str,
    new_label: str,
    profiles: list[str],
    title: str | None = None,
) -> str:
    """Render a markdown table comparing baseline vs new for given profiles."""
    lines = []
    if title:
        lines.append(f"## {title}")
        lines.append("")
    lines.append(
        f"| profile | metric        | {baseline_label} | {new_label} |"
    )
    lines.append("|---------|---------------|-----------------:|------------:|")
    for profile in profiles:
        b = summarize(baseline_path, profile)
        n = summarize(new_path, profile)
        if b is None or n is None:
            lines.append(f"| {profile} | (no data) | - | - |")
            continue
        lines.append(
            f"| {profile} | median rt (s) "
            f"| {b['med_rt']:.3f} | {n['med_rt']:.3f} |"
        )
        lines.append(
            f"| {profile} | best/med ms "
            f"| {_format_makespan(b)} | {_format_makespan(n)} |"
        )
        lines.append(
            f"| {profile} | optimal "
            f"| {b['optimal']}/{b['n']} | {n['optimal']}/{n['n']} |"
        )
    return "\n".join(lines)


def main() -> None:
    """Parse args and print a markdown comparison table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--new", required=True, type=Path)
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--new-label", default="new")
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["small", "medium", "hard", "big"],
    )
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    print(
        render_table(
            args.baseline,
            args.new,
            args.baseline_label,
            args.new_label,
            args.profiles,
            args.title,
        )
    )


if __name__ == "__main__":
    main()
