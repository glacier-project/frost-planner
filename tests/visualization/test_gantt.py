# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

from pathlib import Path
from unittest.mock import Mock

import matplotlib.pyplot as plt
import pytest
from matplotlib.axes import Axes

from frost_planner.core.base import Job, Machine, Task, TaskStatus
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.visualization.gantt import (
    LiveGanttChart,
    _draw_schedule_on_axes,
    plot_gantt_chart,
)


def _task_patches(ax: Axes) -> list:
    return [p for p in ax.patches if getattr(p, "frost_kind", None) == "task"]


def _overrun_patches(ax: Axes) -> list:
    return [
        p for p in ax.patches if getattr(p, "frost_kind", None) == "overrun"
    ]


def _bar_x_ranges(patches: list) -> list[tuple[float, float]]:
    """Sorted (start, end) x-extents of every frost task/overrun patch."""
    out: list[tuple[float, float]] = []
    for p in patches:
        bb = p.get_bbox()
        out.append((float(bb.xmin), float(bb.xmax)))
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

    _draw_schedule_on_axes(ax, schedule, job_color, utilization=False)

    assert ax.get_title(loc="left") == "Schedule"
    assert ax.get_xlim()[1] == 5  # max end_time
    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels == ["M0", "M1"]
    # One task patch per scheduled task
    assert len(_task_patches(ax)) == 3
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


def test_draw_schedule_on_axes_dark_theme_sets_dark_background() -> None:
    """Switching to the dark theme paints axes + figure with the dark
    background."""
    schedule = _build_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, theme="dark")

    # Hex compare via to_hex normalises matplotlib's internal RGBA repr.
    import matplotlib.colors as mcolors

    assert mcolors.to_hex(ax.get_facecolor()) == "#161b22"
    assert mcolors.to_hex(fig.get_facecolor()) == "#0f1419"
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
        assert chart.ax.get_title(loc="left") == "Schedule"
        assert chart.ax.get_xlim()[1] == 5
        assert len(_task_patches(chart.ax)) == 3
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
        first_ids = {id(p) for p in _task_patches(chart.ax)}

        chart.update(_build_alt_schedule())
        second_ids = {id(p) for p in _task_patches(chart.ax)}

        # _build_alt_schedule has 2 tasks
        assert len(_task_patches(chart.ax)) == 2
        # Same-count would also be true if patches were overwritten by
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

    main_bars = _bar_x_ranges(_task_patches(ax))
    assert main_bars == [(0.0, 7.0)]  # extended to current_time
    # Overrun overlay was added as a second patch
    overruns = _overrun_patches(ax)
    assert len(overruns) == 1
    assert _bar_x_ranges(overruns) == [(3.0, 7.0)]  # planned end -> now
    plt.close(fig)


def test_draw_does_not_extend_on_time_in_progress_task() -> None:
    """When current_time is still inside the planned window, no overrun."""
    schedule = _build_single_task_schedule(TaskStatus.IN_PROGRESS)
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, current_time=2)

    main_bars = _bar_x_ranges(_task_patches(ax))
    assert main_bars == [(0.0, 3.0)]  # planned width retained
    # No overrun overlay
    assert _overrun_patches(ax) == []
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

    main_bars = _bar_x_ranges(_task_patches(ax))
    # T0_0 stays at its planned [0, 4]; T0_1 extends to current_time=12.
    assert main_bars == [(0.0, 4.0), (4.0, 12.0)]
    # Only T0_1 produced an overrun overlay.
    overruns = _overrun_patches(ax)
    assert len(overruns) == 1
    assert _bar_x_ranges(overruns) == [(7.0, 12.0)]
    plt.close(fig)


def test_draw_does_not_extend_completed_task() -> None:
    """COMPLETED tasks render at their planned width even when current_time
    is past their scheduled end."""
    schedule = _build_single_task_schedule(TaskStatus.COMPLETED)
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, current_time=7)

    main_bars = _bar_x_ranges(_task_patches(ax))
    assert main_bars == [(0.0, 3.0)]
    assert _overrun_patches(ax) == []
    plt.close(fig)


def _build_idle_schedule() -> Schedule:
    """Three machines, only M0 and M2 have a task; M1 is idle."""
    machines = [Machine(id=f"M{i}", name=f"M{i}") for i in range(3)]
    t0 = Task(id="T0", name="T0", processing_time=4)
    t1 = Task(id="T1", name="T1", processing_time=3)
    _ = Job(id="J0", name="J0", tasks=[t0, t1])
    schedule = Schedule(machines=machines)
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=4, task=t0, machine=machines[0])
    )
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=3, task=t1, machine=machines[2])
    )
    return schedule


def test_idle_hide_drops_machines_without_tasks() -> None:
    schedule = _build_idle_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, idle="hide", utilization=False)

    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels == ["M0", "M2"]  # M1 dropped
    plt.close(fig)


def test_idle_show_keeps_every_machine() -> None:
    schedule = _build_idle_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, idle="show", utilization=False)

    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels == ["M0", "M1", "M2"]
    plt.close(fig)


def test_idle_compress_reports_count_in_subtitle() -> None:
    schedule = _build_idle_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, idle="compress", utilization=False)

    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels == ["M0", "M2"]
    subtitles = [
        t for t in ax.texts if getattr(t, "frost_kind", None) == "subtitle"
    ]
    assert len(subtitles) == 1
    assert "+1 idle" in subtitles[0].get_text()
    plt.close(fig)


def test_utilization_appends_percent_to_y_tick_labels() -> None:
    schedule = _build_idle_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, idle="hide", utilization=True)

    labels = [t.get_text() for t in ax.get_yticklabels()]
    # M0 runs T0 in [0, 4] (makespan = 4), so 100%
    # M2 runs T1 in [0, 3] (makespan = 4), so 75%
    assert labels[0].startswith("M0")
    assert "100%" in labels[0]
    assert labels[1].startswith("M2")
    assert "75%" in labels[1]
    plt.close(fig)


def test_annotation_renders_line_and_pill() -> None:
    """Custom Annotation entries produce a dashed line + labeled pill."""
    from frost_planner.visualization.gantt import Annotation

    schedule = _build_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(
        ax,
        schedule,
        {},
        annotations=[Annotation(time=2, label="deploy")],
    )

    lines = [
        ln
        for ln in ax.lines
        if getattr(ln, "frost_kind", None) == "annotation_line"
    ]
    assert len(lines) == 1
    assert lines[0].get_xdata()[0] == 2
    pills = [
        a
        for a in ax.texts
        if getattr(a, "frost_kind", None) == "annotation_pill"
    ]
    assert len(pills) == 1
    assert pills[0].get_text() == "deploy"
    plt.close(fig)


def test_annotation_accepts_plain_tuples() -> None:
    """`(time, label)` tuples are accepted as shorthand for Annotation."""
    schedule = _build_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(
        ax,
        schedule,
        {},
        annotations=[(1, "start"), (4, "review", "#FF00FF")],
    )

    lines = [
        ln
        for ln in ax.lines
        if getattr(ln, "frost_kind", None) == "annotation_line"
    ]
    assert len(lines) == 2
    pills = [
        a
        for a in ax.texts
        if getattr(a, "frost_kind", None) == "annotation_pill"
    ]
    labels = sorted(p.get_text() for p in pills)
    assert labels == ["review", "start"]
    plt.close(fig)


def test_annotation_rejects_malformed_entries() -> None:
    schedule = _build_schedule()
    fig, ax = plt.subplots()

    with pytest.raises(TypeError):
        _draw_schedule_on_axes(
            ax,
            schedule,
            {},
            annotations=[(1,)],
        )
    plt.close(fig)


def test_legend_uses_job_names_when_jobs_provided() -> None:
    schedule = _build_idle_schedule()
    job = Job(id="J0", name="Alpha", tasks=[])
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, jobs=[job])

    legend = ax.get_legend()
    assert legend is not None
    labels = [t.get_text() for t in legend.get_texts()]
    assert "Alpha" in labels
    plt.close(fig)


def test_legend_falls_back_to_id_prefix_without_jobs() -> None:
    schedule = _build_idle_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {})

    legend = ax.get_legend()
    assert legend is not None
    labels = [t.get_text() for t in legend.get_texts()]
    assert any(label.startswith("Job ") for label in labels)
    plt.close(fig)


def test_palette_override_assigns_supplied_colors() -> None:
    schedule = _build_idle_schedule()
    fig, ax = plt.subplots()
    palette = ["#FF0000", "#00FF00"]
    job_color: dict[str, tuple] = {}

    _draw_schedule_on_axes(ax, schedule, job_color, palette=palette)

    # Tuple form, RGBA, with R≈1.0 (first palette entry)
    r, g, b, _ = job_color["J0"]
    assert (r, g, b) == (1.0, 0.0, 0.0)
    plt.close(fig)


def test_late_task_renders_corner_flag() -> None:
    """A task ending past its job's due_date gets a Polygon flag artist."""
    m0 = Machine(id="M0", name="M0")
    t = Task(id="T0", name="T0", processing_time=5)
    job = Job(id="J0", name="J0", tasks=[t], due_date=3)
    schedule = Schedule(machines=[m0])
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=5, task=t, machine=m0)
    )
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, jobs=[job])

    flags = [
        p for p in ax.patches if getattr(p, "frost_kind", None) == "late_flag"
    ]
    assert len(flags) == 1
    plt.close(fig)


def test_on_time_task_has_no_late_flag() -> None:
    m0 = Machine(id="M0", name="M0")
    t = Task(id="T0", name="T0", processing_time=3)
    job = Job(id="J0", name="J0", tasks=[t], due_date=10)
    schedule = Schedule(machines=[m0])
    schedule.add_scheduled_task(
        ScheduledTask(start_time=0, end_time=3, task=t, machine=m0)
    )
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {}, jobs=[job])

    flags = [
        p for p in ax.patches if getattr(p, "frost_kind", None) == "late_flag"
    ]
    assert flags == []
    plt.close(fig)


def test_subtitle_reports_machine_task_makespan_counts() -> None:
    schedule = _build_schedule()
    fig, ax = plt.subplots()

    _draw_schedule_on_axes(ax, schedule, {})

    subs = [t for t in ax.texts if getattr(t, "frost_kind", None) == "subtitle"]
    assert len(subs) == 1
    text = subs[0].get_text()
    assert "2 machines" in text
    assert "3 tasks" in text
    assert "makespan 5" in text
    plt.close(fig)


def test_plot_gantt_chart_auto_sizes_when_figsize_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting figsize triggers row-count-based auto sizing."""
    monkeypatch.setattr(plt, "show", Mock())
    schedule = _build_schedule()  # 2 active machines
    out = tmp_path / "chart.png"

    plot_gantt_chart(schedule, output_path=str(out))

    assert out.exists()
    plt.close("all")
