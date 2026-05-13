# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations

import argparse

import matplotlib

from frost_planner.core.base import (
    Job,
    Machine,
    SchedulingInstance,
    Task,
    TaskStatus,
)
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.visualization.gantt import LiveGanttChart


def _build_overlapping_in_progress_schedule(current_time: int) -> tuple[
    SchedulingInstance, Schedule
]:
    """Two consecutive tasks on M0, both marked IN_PROGRESS at t=12.

    Task A is planned for [0, 4] and Task B for [4, 7]. Neither is
    completed.
    """
    m0 = Machine(id="M0", name="M0", capabilities=["cap"])

    a = Task(
        id="T0_0",
        name="T0_0",
        processing_time=4,
        requires=["cap"],
        status=TaskStatus.IN_PROGRESS,
    )
    b = Task(
        id="T0_1",
        name="T0_1",
        processing_time=3,
        requires=["cap"],
        dependencies=["T0_0"],
        status=TaskStatus.READY,
    )
    job = Job(id="J0", name="J0", tasks=[a, b])

    instance = SchedulingInstance(machines=[m0], jobs=[job])
    schedule = Schedule(machines=[m0])
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=4, task=a, machine=m0)
    )
    schedule.add_scheduled_task(
        ScheduledTask(
            start_time=current_time,
            end_time=current_time + b.processing_time,
            task=b,
            machine=m0
        )
    )
    return instance, schedule


def main() -> None:
    """Render the demo schedule and report label positions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="If set, write the figure to this path instead of showing it.",
    )
    args = parser.parse_args()

    if args.save:
        matplotlib.use("Agg")

    _, schedule = _build_overlapping_in_progress_schedule(current_time=12)

    chart = LiveGanttChart()
    chart.update(schedule, current_time=12)

    # With the clamp:
    #   - T0_0 (planned [0, 4]) keeps its planned width because the next
    #     task starts at t=4, so its bar stops at 4.
    #   - T0_1 (planned [4, 7]) is the latest task on M0, so it extends
    #     all the way to t=12 with the hatched overrun overlay drawn
    #     over [7, 12].
    label_positions = sorted(
        (t.get_position()[0], t.get_text())
        for t in chart.ax.texts
        if t.get_text()
    )
    print("Label positions on M0:")
    for x, label in label_positions:
        print(f"  x={x:>5.2f}  {label}")

    if args.save:
        chart.fig.savefig(args.save)
        print(f"\nFigure written to {args.save}")
        chart.close()
    else:
        import matplotlib.pyplot as plt

        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()
