# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

from pathlib import Path
from unittest.mock import Mock

import matplotlib.pyplot as plt
import pytest

from frost_planner.core.base import Job, Machine, Task, TaskStatus
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.visualization.gantt import (
    LiveGanttChart,
    _draw_schedule_on_axes,
    plot_gantt_chart,
)


def _bar_x_ranges(collection: object) -> list[tuple[float, float]]:
    """Return sorted (start, end) x-extents of every rectangle in a
    `broken_barh` collection."""
    out: list[tuple[float, float]] = []
    for path in collection.get_paths():  # type: ignore[attr-defined]
        xs = path.vertices[:, 0]
        out.append((float(xs.min()), float(xs.max())))
    return sorted(out)


def _build_schedule() -> Schedule:
    """Build a tiny 2-machine, 2-job schedule the gantt code can render.

    Task names follow the `Tj_t` convention the gantt code parses:
    name[-3:-2] is the job id, name[-1] is the task id.
    """
    m0 = Machine(id="M0", name="M0")
    m1 = Machine(id="M1", name="M1")

    t00 = Task(id="T0_0", name="T0_0", processing_time=3)
    t01 = Task(id="T0_1", name="T0_1", processing_time=2)
    t10 = Task(id="T1_0", name="T1_0", processing_time=4)

    _ = Job(id="J0", name="J0", tasks=[t00, t01, t10])

    schedule = Schedule()
    schedule.machines = [m0, m1]
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=3, task=t00, machine=m0)
    )
    schedule.add_scheduled_task(
        ScheduledTask(start_time=3, end_time=5, task=t01, machine=m1)
    )
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=4, task=t10, machine=m0)
    )
    return schedule


def test_draw_schedule_on_axes_populates_axes() -> None:
    """Helper sets title, x-limit, y-tick labels, and draws bars."""
    schedule = _build_schedule()
    fig, ax = plt.subplots()
    job_color: dict[str, tuple] = {}

    _draw_schedule_on_axes(ax, schedule, job_color)

    assert ax.get_title() == "Schedule"
    assert ax.get_xlim()[1] == 5  # max end_time
    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels == ["M0", "M1"]
    # One BrokenBarHCollection per machine row
    assert len(ax.collections) == 2
    plt.close(fig)


def test_draw_schedule_on_axes_mutates_job_color() -> None:
    """Helper records a color for each distinct job id seen."""
    schedule = _build_schedule()
    fig, ax = plt.subplots()
    job_color: dict[str, tuple] = {}

    _draw_schedule_on_axes(ax, schedule, job_color)

    assert set(job_color.keys()) == {"J0"}
    plt.close(fig)


def test_draw_schedule_on_axes_reuses_existing_colors() -> None:
    """A pre-populated job_color entry is preserved."""
    schedule = _build_schedule()
    fig, ax = plt.subplots()
    sentinel = (0.1, 0.2, 0.3, 1.0)
    job_color: dict[str, tuple] = {"J0": sentinel}

    _draw_schedule_on_axes(ax, schedule, job_color)

    assert job_color["J0"] == sentinel
    plt.close(fig)


def test_plot_gantt_chart_saves_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wrapper writes the figure to output_path when provided."""
    monkeypatch.setattr(plt, "show", Mock())
    schedule = _build_schedule()
    out = tmp_path / "chart.png"

    plot_gantt_chart(schedule, output_path=str(out))

    assert out.exists()
    assert out.stat().st_size > 0


def _build_alt_schedule() -> Schedule:
    """A second schedule with the same jobs but shifted timings."""
    m0 = Machine(id="M0", name="M0")
    m1 = Machine(id="M1", name="M1")

    t00 = Task(id="T0_0", name="T0_0", processing_time=2)
    t10 = Task(id="T1_0", name="T1_0", processing_time=5)

    schedule = Schedule()
    schedule.machines = [m0, m1]
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=2, task=t00, machine=m0)
    )
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=5, task=t10, machine=m1)
    )
    return schedule


def test_live_gantt_chart_init_creates_empty_state() -> None:
    chart = LiveGanttChart()
    try:
        assert chart.fig is not None
        assert chart.ax is not None
        assert chart._job_color == {}
    finally:
        chart.close()


def test_live_gantt_chart_update_draws_schedule() -> None:
    chart = LiveGanttChart()
    try:
        chart.update(_build_schedule())
        assert chart.ax.get_title() == "Schedule"
        assert chart.ax.get_xlim()[1] == 5
        assert len(chart.ax.collections) == 2
        assert set(chart._job_color.keys()) == {"J0"}
    finally:
        chart.close()


def test_live_gantt_chart_persists_colors_across_updates() -> None:
    """Same job id keeps the same color when a second schedule is pushed."""
    chart = LiveGanttChart()
    try:
        chart.update(_build_schedule())
        first_colors = dict(chart._job_color)

        chart.update(_build_alt_schedule())

        for job_id, color in first_colors.items():
            assert chart._job_color[job_id] == color
    finally:
        chart.close()


def test_live_gantt_chart_update_clears_previous_artists() -> None:
    """A second update should detach the prior artists, not overwrite them."""
    chart = LiveGanttChart()
    try:
        chart.update(_build_schedule())
        first_ids = {id(c) for c in chart.ax.collections}

        chart.update(_build_alt_schedule())
        second_ids = {id(c) for c in chart.ax.collections}

        assert len(chart.ax.collections) == 2
        # Same-count would also be true if collections were overwritten by
        # reference; identity-disjointness proves ax.clear() really detached.
        assert first_ids.isdisjoint(second_ids)
    finally:
        chart.close()


def test_live_gantt_chart_close_closes_figure() -> None:
    chart = LiveGanttChart()
    fig_num = chart.fig.number
    chart.close()
    assert not plt.fignum_exists(fig_num)


def _build_single_task_schedule(status: TaskStatus) -> Schedule:
    """One IN_PROGRESS task on one machine, scheduled in [0, 3]."""
    m0 = Machine(id="M0", name="M0")
    t = Task(id="T0_0", name="T0_0", processing_time=3, status=status)
    _ = Job(id="J0", name="J0", tasks=[t])
    schedule = Schedule()
    schedule.machines = [m0]
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=3, task=t, machine=m0)
    )
    return schedule


def test_draw_extends_in_progress_task_past_scheduled_end() -> None:
    """An IN_PROGRESS task whose scheduled end is in the past renders as
    long as it has actually been running."""
    schedule = _build_single_task_schedule(TaskStatus.IN_PROGRESS)
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, current_time=7)

    main_bars = _bar_x_ranges(ax.collections[0])
    assert main_bars == [(0.0, 7.0)]  # extended to current_time
    # Overrun overlay was added as a second collection
    assert len(ax.collections) == 2
    overrun_bars = _bar_x_ranges(ax.collections[1])
    assert overrun_bars == [(3.0, 7.0)]  # covers planned end -> now
    plt.close(fig)


def test_draw_does_not_extend_on_time_in_progress_task() -> None:
    """When current_time is still inside the planned window, no overrun."""
    schedule = _build_single_task_schedule(TaskStatus.IN_PROGRESS)
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, current_time=2)

    main_bars = _bar_x_ranges(ax.collections[0])
    assert main_bars == [(0.0, 3.0)]  # planned width retained
    # No overrun overlay
    assert len(ax.collections) == 1
    plt.close(fig)


def test_draw_clamps_overrun_to_next_task_start() -> None:
    """When two IN_PROGRESS tasks sit back-to-back on the same machine,
    the earlier one keeps its planned width and only the later one
    extends to current_time, so their bars do not overlap."""
    m0 = Machine(id="M0", name="M0")
    a = Task(
        id="T0_0",
        name="T0_0",
        processing_time=4,
        status=TaskStatus.IN_PROGRESS,
    )
    b = Task(
        id="T0_1",
        name="T0_1",
        processing_time=3,
        dependencies=["T0_0"],
        status=TaskStatus.IN_PROGRESS,
    )
    _ = Job(id="J0", name="J0", tasks=[a, b])
    schedule = Schedule()
    schedule.machines = [m0]
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=4, task=a, machine=m0)
    )
    schedule.add_scheduled_task(
        ScheduledTask(start_time=4, end_time=7, task=b, machine=m0)
    )

    fig, ax = plt.subplots()
    _draw_schedule_on_axes(ax, schedule, {}, current_time=12)

    main_bars = _bar_x_ranges(ax.collections[0])
    # T0_0 stays at its planned [0, 4]; T0_1 extends to current_time=12.
    assert main_bars == [(0.0, 4.0), (4.0, 12.0)]
    # Only T0_1 produced an overrun overlay.
    assert len(ax.collections) == 2
    overrun_bars = _bar_x_ranges(ax.collections[1])
    assert overrun_bars == [(7.0, 12.0)]
    plt.close(fig)


def test_draw_does_not_extend_completed_task() -> None:
    """COMPLETED tasks render at their planned width even when current_time
    is past their scheduled end."""
    schedule = _build_single_task_schedule(TaskStatus.COMPLETED)
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, current_time=7)

    main_bars = _bar_x_ranges(ax.collections[0])
    assert main_bars == [(0.0, 3.0)]
    assert len(ax.collections) == 1
    plt.close(fig)
