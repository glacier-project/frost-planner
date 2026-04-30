from unittest.mock import Mock

import matplotlib.pyplot as plt

from frost_planner.core.base import Machine, Task, Job
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.visualization.gantt import (
    LiveGanttChart,
    _draw_schedule_on_axes,
    plot_gantt_chart,
)


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
    
    j00 = Job(id="J0", name="J0", tasks=[t00, t01, t10])

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


def test_plot_gantt_chart_saves_to_path(tmp_path, monkeypatch) -> None:
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
