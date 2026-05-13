# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import FancyBboxPatch, Polygon
from matplotlib.ticker import MaxNLocator

from frost_planner.core.base import Job, TaskStatus
from frost_planner.core.schedule import Schedule
from frost_planner.utils import cprint

ThemeName = Literal["light", "dark"]
IdleMode = Literal["hide", "compress", "show"]

# Vertical layout
_Y_START = 0.5
_Y_DELTA = 1.0
_BAR_WIDTH = 0.62
_BAR_RADIUS = 0.22

# Bars narrower than this fraction of the time axis get no inline label.
_LABEL_MIN_FRAC = 0.035

# Highlighting (click-to-focus): alpha applied to non-selected bars.
_DIM_ALPHA = 0.18


@dataclass(frozen=True)
class _Theme:
    fig_bg: str
    axes_bg: str
    text: str
    text_muted: str
    grid: str
    row_stripe: str
    bar_edge: str
    now_line: str
    now_label_text: str
    palette: tuple[str, ...]
    overrun_edge: str
    late_flag: str
    annotation_line: str           # default color for custom annotation marks
    annotation_label_text: str     # text color shown on the annotation pill


_LIGHT = _Theme(
    fig_bg="#FFFFFF",
    axes_bg="#FFFFFF",
    text="#1F2933",
    text_muted="#52606D",
    grid="#E4E7EB",
    row_stripe="#F7F8FA",
    bar_edge="#FFFFFF",
    now_line="#FF6B6B",
    now_label_text="#FFFFFF",
    palette=(
        "#4E79A7",
        "#F28E2B",
        "#59A14F",
        "#E15759",
        "#76B7B2",
        "#EDC948",
        "#B07AA1",
        "#FF9DA7",
        "#9C755F",
        "#BAB0AC",
    ),
    overrun_edge="#52606D",
    late_flag="#D7263D",
    annotation_line="#3D5A80",
    annotation_label_text="#FFFFFF",
)

_DARK = _Theme(
    fig_bg="#0F1419",
    axes_bg="#161B22",
    text="#E6EDF3",
    text_muted="#B3BCC8",
    grid="#262C36",
    row_stripe="#1B2129",
    bar_edge="#161B22",
    now_line="#FF8FA3",
    now_label_text="#0F1419",
    palette=(
        "#79B8FF",
        "#FFB870",
        "#85E89D",
        "#FF7B72",
        "#7EE3DC",
        "#FFEA7F",
        "#D2A8FF",
        "#FFBFC6",
        "#C9B287",
        "#C9D1D9",
    ),
    overrun_edge="#8B949E",
    late_flag="#FF6B7A",
    annotation_line="#9DB5D6",
    annotation_label_text="#0F1419",
)

_THEMES: dict[ThemeName, _Theme] = {"light": _LIGHT, "dark": _DARK}


@dataclass(frozen=True)
class Annotation:
    """A vertical event marker drawn on the Gantt timeline.

    Attributes:
        time: x-position (in the same units as the schedule's times).
        label: short text shown in a pill at the top of the line.
        color: optional accent color; defaults to a theme-derived neutral.
    """

    time: float
    label: str
    color: str | None = None


AnnotationLike = "Annotation | tuple[float, str] | tuple[float, str, str]"


def _normalize_annotations(items: list | None) -> list[Annotation]:
    if not items:
        return []
    out: list[Annotation] = []
    for a in items:
        if isinstance(a, Annotation):
            out.append(a)
        elif isinstance(a, tuple) and len(a) == 2:
            out.append(Annotation(time=float(a[0]), label=str(a[1])))
        elif isinstance(a, tuple) and len(a) == 3:
            out.append(
                Annotation(time=float(a[0]), label=str(a[1]), color=str(a[2]))
            )
        else:
            raise TypeError(
                "annotation entries must be Annotation or "
                "(time, label[, color]) tuples"
            )
    return out


def _machine_utilization(
    solution: Schedule, machine_id: str, denom: float
) -> float:
    """Return busy_time / denom for a machine, clamped to [0, 1]."""
    if denom <= 0:
        return 0.0
    busy = sum(
        (st.end_time - st.start_time)
        for st in solution.mapping.get(machine_id, [])
    )
    return max(0.0, min(1.0, busy / denom))


def _palette_color(
    index: int, palette: tuple[str, ...]
) -> tuple[float, float, float, float]:
    rgb = mcolors.to_rgb(palette[index % len(palette)])
    return (*rgb, 1.0)


def _darken(rgb: tuple[float, ...], amount: float) -> tuple[float, float, float]:
    r, g, b = rgb[:3]
    return (r * (1 - amount), g * (1 - amount), b * (1 - amount))


def _lighten(rgb: tuple[float, ...], amount: float) -> tuple[float, float, float]:
    r, g, b = rgb[:3]
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount)


def _running_accent(
    color: tuple[float, ...], theme: _Theme
) -> tuple[float, float, float]:
    rgb = mcolors.to_rgb(color)
    if theme is _DARK:
        return _lighten(rgb, 0.45)
    return _darken(rgb, 0.40)


def _text_on(color: tuple[float, ...], theme: _Theme) -> str:
    r, g, b = mcolors.to_rgb(color)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if luminance > 0.58:
        return theme.text
    return "#FFFFFF" if theme is _LIGHT else theme.text


def _autosize(n_rows: int, width: float = 12.0) -> tuple[float, float]:
    """Compute a sensible figsize for `n_rows` machines on the y-axis."""
    return (width, max(3.0, 0.45 * max(n_rows, 1) + 1.5))


def _resolve_jobs(jobs: list[Job] | None) -> dict[str, Job]:
    return {j.id: j for j in jobs} if jobs else {}


def _job_label(jid: str, jobs_by_id: dict[str, Job]) -> str:
    job = jobs_by_id.get(jid)
    if job and job.name:
        return job.name
    return f"Job {jid[:8]}"


def _draw_schedule_on_axes(
    ax: Axes,
    solution: Schedule,
    job_color: dict[str, tuple],
    current_time: int | None = None,
    theme: ThemeName = "light",
    *,
    idle: IdleMode = "hide",
    jobs: list[Job] | None = None,
    palette: tuple[str, ...] | list[str] | None = None,
    annotations: list | None = None,
    utilization: bool = True,
) -> None:
    """Draw a Gantt-style view of `solution` onto `ax`.

    Args:
        ax: matplotlib axes to draw on (cleared callers re-apply state on each
            call).
        solution: schedule to render.
        job_color: mutable map of job id -> RGBA color (mutated in place so
            colors stay stable across redraws).
        current_time: optional "now" marker.
        theme: "light" or "dark".
        idle: behavior for machines with no scheduled tasks. "hide" (default)
            drops them, "compress" drops them but adds an "+N idle" footnote,
            "show" keeps all machines visible.
        jobs: optional Job objects, used to resolve readable names and to
            shade late tasks (those whose end_time exceeds their job's
            due_date).
        palette: optional override of the theme's categorical color list.
    """
    th = _THEMES[theme]
    pal = tuple(palette) if palette else th.palette
    ax.figure.patch.set_facecolor(th.fig_bg)
    ax.set_facecolor(th.axes_bg)

    jobs_by_id = _resolve_jobs(jobs)

    # Decide which machines to render
    all_machines = list(solution.machines)
    has_work = {
        m.id
        for m in all_machines
        if solution.mapping.get(m.id)
    }
    if idle == "show":
        machines = all_machines
    else:
        machines = [m for m in all_machines if m.id in has_work]
    n_idle = len(all_machines) - len(machines)

    tasks_all = solution.get_tasks()
    makespan = max((st.end_time for st in tasks_all), default=0)
    x_max = makespan or 100
    if current_time is not None:
        x_max = max(x_max, current_time)

    n_machines = len(machines)
    y_ticks = [(i * _Y_DELTA) + _Y_START for i in range(n_machines)]
    ax.set_yticks(y_ticks)
    if utilization and makespan > 0:
        tick_labels = [
            f"{m.name}  ·  "
            f"{int(round(_machine_utilization(solution, m.id, makespan) * 100))}%"
            for m in machines
        ]
    else:
        tick_labels = [m.name for m in machines]
    ax.set_yticklabels(tick_labels)
    ax.set_xlim(0, x_max)
    if n_machines:
        ax.set_ylim(
            _Y_START - _Y_DELTA / 2,
            (n_machines - 1) * _Y_DELTA + _Y_START + _Y_DELTA / 2,
        )

    # Title + subtitle + axis labels.
    # Vertical stacking above the data top edge depends on what is shown:
    # - "Now" pill (if current_time set) always lives at the +6pt row.
    # - Annotation pills join the same row when "Now" is absent, otherwise
    #   they shift to a row above it.
    # - Subtitle sits above the highest pill row.
    # - Title pad is bumped to clear the subtitle.
    has_now = current_time is not None and n_machines > 0
    annots_pre = _normalize_annotations(annotations)
    has_annots = bool(annots_pre) and n_machines > 0
    annot_offset_pt = 24 if (has_now and has_annots) else 6
    subtitle_offset_pt = 22 + (18 if has_now and has_annots else 0)
    title_pad_pt = 42 + (18 if has_now and has_annots else 0)

    ax.set_title(
        "Schedule",
        color=th.text,
        fontsize=15,
        fontweight="bold",
        loc="left",
        pad=title_pad_pt,
    )
    subtitle_bits = [
        f"{n_machines} machine{'s' if n_machines != 1 else ''}",
        f"{len(tasks_all)} task{'s' if len(tasks_all) != 1 else ''}",
        f"makespan {makespan}",
    ]
    if idle == "compress" and n_idle:
        subtitle_bits.append(f"+{n_idle} idle")
    subtitle_artist = ax.annotate(
        " · ".join(subtitle_bits),
        xy=(0, 1.0),
        xycoords=ax.transAxes,
        xytext=(0, subtitle_offset_pt),
        textcoords="offset points",
        ha="left", va="bottom",
        color=th.text_muted,
        fontsize=10,
    )
    subtitle_artist.frost_kind = "subtitle"  # type: ignore[attr-defined]
    ax.set_xlabel("Time", color=th.text_muted, fontsize=10, labelpad=8)
    ax.set_ylabel("")

    # Spines
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(th.grid)
    ax.spines["bottom"].set_linewidth(0.8)

    # Ticks
    ax.tick_params(axis="x", colors=th.text_muted, labelsize=9, length=0, pad=6)
    ax.tick_params(axis="y", colors=th.text, labelsize=10, length=0, pad=8)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True, prune="both"))

    # Grid
    ax.grid(True, axis="x", which="major",
            color=th.grid, linewidth=0.8, alpha=1.0, linestyle="-")
    ax.set_axisbelow(True)

    # Zebra row stripes
    for i in range(n_machines):
        if i % 2 == 1:
            stripe = ax.axhspan(
                i * _Y_DELTA + _Y_START - _Y_DELTA / 2,
                i * _Y_DELTA + _Y_START + _Y_DELTA / 2,
                facecolor=th.row_stripe,
                edgecolor="none",
                zorder=0.2,
            )
            stripe.frost_kind = "row_stripe"  # type: ignore[attr-defined]

    # Now indicator
    if current_time is not None and n_machines:
        ax.axvline(
            x=current_time, color=th.now_line,
            linewidth=1.5, alpha=0.9, zorder=3.5,
        )
        y_top = (n_machines - 1) * _Y_DELTA + _Y_START + _Y_DELTA / 2
        ax.annotate(
            "Now",
            xy=(current_time, y_top),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center", va="bottom",
            fontsize=8.5, fontweight="bold",
            color=th.now_label_text,
            bbox={
                "boxstyle": "round,pad=0.32",
                "facecolor": th.now_line,
                "edgecolor": "none",
            },
            zorder=4.0,
        )

    # Custom annotation markers (deploys, shift changes, milestones, ...)
    if has_annots:
        y_top = (n_machines - 1) * _Y_DELTA + _Y_START + _Y_DELTA / 2
        for a in annots_pre:
            color = a.color or th.annotation_line
            line = ax.axvline(
                x=a.time, color=color,
                linewidth=1.0, linestyle=(0, (4, 3)),
                alpha=0.85, zorder=3.2,
            )
            line.frost_kind = "annotation_line"  # type: ignore[attr-defined]
            pill = ax.annotate(
                a.label,
                xy=(a.time, y_top),
                xytext=(0, annot_offset_pt),
                textcoords="offset points",
                ha="center", va="bottom",
                fontsize=8.5, fontweight="bold",
                color=th.annotation_label_text,
                bbox={
                    "boxstyle": "round,pad=0.32",
                    "facecolor": color,
                    "edgecolor": "none",
                },
                zorder=3.8,
            )
            pill.frost_kind = "annotation_pill"  # type: ignore[attr-defined]

    machine_idx = {m.id: i for i, m in enumerate(machines)}

    any_overrun = False
    any_running = False
    any_completed = False
    any_late = False

    # Track which job ids actually appear (so legend is exact)
    seen_jobs: set[str] = set()

    for machine_id, tasks in solution.mapping.items():
        if machine_id not in machine_idx:
            continue
        i = machine_idx[machine_id]
        sorted_tasks = sorted(tasks, key=lambda st: st.start_time)
        y_bottom = i * _Y_DELTA + _Y_START - _BAR_WIDTH / 2

        for idx, t in enumerate(sorted_tasks):
            jid = str(t.task.job_id)
            seen_jobs.add(jid)
            if jid not in job_color:
                job_color[jid] = _palette_color(len(job_color), pal)
            color = job_color[jid]

            displayed_width = t.task.processing_time
            overrun_extra: tuple[float, float] | None = None
            if (
                current_time is not None
                and t.task.status == TaskStatus.IN_PROGRESS
                and current_time > t.end_time
            ):
                next_start = (
                    sorted_tasks[idx + 1].start_time
                    if idx + 1 < len(sorted_tasks)
                    else current_time
                )
                cap = min(current_time, next_start)
                if cap > t.end_time:
                    displayed_width = cap - t.start_time
                    overrun_extra = (t.end_time, cap - t.end_time)
                    any_overrun = True

            # Lateness: does this task's end push past its job's due_date?
            job_obj = jobs_by_id.get(jid)
            is_late = (
                job_obj is not None
                and job_obj.due_date is not None
                and t.end_time > job_obj.due_date
            )
            if is_late:
                any_late = True

            # Status styling
            if t.task.status == TaskStatus.IN_PROGRESS:
                fill: tuple = color
                edge = _running_accent(color, th)
                lw = 1.6
                label_text = t.task.name
                any_running = True
            elif t.task.status == TaskStatus.COMPLETED:
                fill = color
                edge = th.bar_edge
                lw = 1.0
                label_text = f"✓ {t.task.name}"
                any_completed = True
            else:
                r, g, b, _ = mcolors.to_rgba(color)
                fill = (r, g, b, 0.85)
                edge = th.bar_edge
                lw = 1.0
                label_text = t.task.name

            bar = FancyBboxPatch(
                (t.start_time, y_bottom),
                displayed_width,
                _BAR_WIDTH,
                boxstyle=f"round,pad=0,rounding_size={_BAR_RADIUS}",
                facecolor=fill,
                edgecolor=edge,
                linewidth=lw,
                joinstyle="round",
                zorder=2.0,
            )
            bar.frost_kind = "task"  # type: ignore[attr-defined]
            bar.frost_status = t.task.status  # type: ignore[attr-defined]
            bar.frost_machine = machine_id  # type: ignore[attr-defined]
            bar.frost_task_id = t.task.id  # type: ignore[attr-defined]
            bar.frost_job_id = jid  # type: ignore[attr-defined]
            bar.frost_task_name = t.task.name  # type: ignore[attr-defined]
            bar.frost_start = t.start_time  # type: ignore[attr-defined]
            bar.frost_end = t.end_time  # type: ignore[attr-defined]
            ax.add_patch(bar)

            if overrun_extra is not None:
                ox, ow = overrun_extra
                overlay = FancyBboxPatch(
                    (ox, y_bottom),
                    ow,
                    _BAR_WIDTH,
                    boxstyle=f"round,pad=0,rounding_size={_BAR_RADIUS}",
                    facecolor="none",
                    edgecolor=th.overrun_edge,
                    linewidth=0.9,
                    hatch="//",
                    zorder=2.4,
                )
                overlay.frost_kind = "overrun"  # type: ignore[attr-defined]
                overlay.frost_job_id = jid  # type: ignore[attr-defined]
                ax.add_patch(overlay)

            if is_late:
                # Triangular "late" flag in the top-right corner of the bar.
                flag_size = min(_BAR_WIDTH * 0.5, displayed_width * 0.3)
                # x-axis is in time units; pick a tasteful absolute size
                # capped by both bar dims.
                flag_x = min(flag_size, max(1.0, 0.02 * x_max))
                flag_x = min(flag_x, displayed_width)
                flag_y = min(flag_size, _BAR_WIDTH * 0.5)
                right = t.start_time + displayed_width
                top = y_bottom + _BAR_WIDTH
                flag = Polygon(
                    [
                        (right - flag_x, top),
                        (right, top - flag_y),
                        (right, top),
                    ],
                    closed=True,
                    facecolor=th.late_flag,
                    edgecolor="none",
                    zorder=2.7,
                )
                flag.frost_kind = "late_flag"  # type: ignore[attr-defined]
                flag.frost_job_id = jid  # type: ignore[attr-defined]
                ax.add_patch(flag)

            if x_max > 0 and displayed_width >= _LABEL_MIN_FRAC * x_max:
                lbl = ax.text(
                    t.start_time + displayed_width / 2,
                    i * _Y_DELTA + _Y_START,
                    label_text,
                    ha="center", va="center",
                    fontsize=9,
                    color=_text_on(color, th),
                    zorder=2.6,
                )
                lbl.frost_kind = "task_label"  # type: ignore[attr-defined]
                lbl.frost_job_id = jid  # type: ignore[attr-defined]

    # Legend
    handles: list[mpatches.Patch] = []
    for jid in sorted(seen_jobs):
        handles.append(
            mpatches.Patch(
                facecolor=job_color[jid],
                edgecolor="none",
                label=_job_label(jid, jobs_by_id),
            )
        )
    if any_running:
        sample = _palette_color(0, pal)
        handles.append(
            mpatches.Patch(
                facecolor=sample,
                edgecolor=_running_accent(sample, th),
                linewidth=1.6,
                label="Running",
            )
        )
    if any_completed:
        handles.append(
            mpatches.Patch(
                facecolor=_palette_color(0, pal),
                edgecolor="none",
                label="✓ Completed",
            )
        )
    if any_overrun:
        handles.append(
            mpatches.Patch(
                facecolor="none",
                edgecolor=th.overrun_edge,
                hatch="//",
                label="Overrun",
            )
        )
    if any_late:
        handles.append(
            mpatches.Patch(
                facecolor=th.late_flag,
                edgecolor="none",
                label="Late",
            )
        )

    if handles:
        legend = ax.legend(
            handles=handles,
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            frameon=False,
            fontsize=9,
            handlelength=1.4,
            handleheight=1.0,
            borderaxespad=0.0,
            labelspacing=0.7,
        )
        for text in legend.get_texts():
            text.set_color(th.text_muted)


def _focus_artists(ax: Axes) -> list:
    """All artists whose alpha is steered by the click-to-focus highlight."""
    items: list = []
    for p in ax.patches:
        if getattr(p, "frost_kind", None) in {"task", "overrun", "late_flag"}:
            items.append(p)
    for t in ax.texts:
        if getattr(t, "frost_kind", None) == "task_label":
            items.append(t)
    return items


def _apply_focus(ax: Axes, target_job: str | None) -> None:
    """Dim every focus-able artist whose ``frost_job_id`` doesn't match
    ``target_job``. Pass ``None`` to clear the dimming.
    """
    for art in _focus_artists(ax):
        jid = getattr(art, "frost_job_id", None)
        art.set_alpha(1.0 if target_job is None or jid == target_job else _DIM_ALPHA)
    ax.figure.canvas.draw_idle()


def _attach_hover(ax: Axes):  # type: ignore[no-untyped-def]
    """If mplcursors is available, attach a hover tooltip showing task info.

    Returns the created ``mplcursors.Cursor`` instance (or ``None`` if the
    library isn't installed / there's nothing to hover over) so callers can
    dispose of it across redraws via ``cursor.remove()``.
    """
    try:
        import mplcursors  # type: ignore[import-not-found]
        from mplcursors import _pick_info  # type: ignore[import-not-found]
    except ImportError:
        return None

    # mplcursors ships pick handlers for Rectangle/Polygon/PathPatch but not
    # FancyBboxPatch. Register one (idempotent) that reuses the same path-based
    # projection logic those handlers use.
    if FancyBboxPatch not in _pick_info.compute_pick.registry:
        _pick_info.compute_pick.register(FancyBboxPatch)(
            _pick_info.compute_pick.registry[Polygon]
        )

    targets = [p for p in ax.patches if getattr(p, "frost_kind", None) == "task"]
    if not targets:
        return None

    cursor = mplcursors.cursor(targets, hover=True)

    @cursor.connect("add")
    def _on_add(sel):  # type: ignore[no-untyped-def]
        p = sel.artist
        name = getattr(p, "frost_task_name", "task")
        start = getattr(p, "frost_start", None)
        end = getattr(p, "frost_end", None)
        machine = getattr(p, "frost_machine", None)
        status = getattr(p, "frost_status", None)
        lines = [name]
        if start is not None and end is not None:
            lines.append(f"{start} → {end}  (Δ {end - start})")
        if machine is not None:
            lines.append(f"machine: {machine}")
        if status is not None:
            lines.append(f"status: {getattr(status, 'value', status)}")
        sel.annotation.set_text("\n".join(lines))
        sel.annotation.get_bbox_patch().set(fc="white", alpha=0.95, ec="none")

    return cursor


def _attach_click_highlight(ax: Axes) -> None:
    """Clicking a task bar dims every bar whose job differs; click empty to reset.

    The currently-focused job id is persisted on ``ax._frost_focused_job`` so
    the highlight can be re-applied to fresh artists after ``ax.clear()`` (the
    custom attribute survives ``clear``).
    """
    fig = ax.figure
    if not hasattr(ax, "_frost_focused_job"):
        ax._frost_focused_job = None  # type: ignore[attr-defined]

    def _on_click(event) -> None:  # type: ignore[no-untyped-def]
        if event.inaxes is not ax or event.button != 1:
            return
        for p in ax.patches:
            if getattr(p, "frost_kind", None) != "task":
                continue
            contains, _ = p.contains(event)
            if contains:
                target = getattr(p, "frost_job_id", None)
                ax._frost_focused_job = target  # type: ignore[attr-defined]
                _apply_focus(ax, target)
                return
        ax._frost_focused_job = None  # type: ignore[attr-defined]
        _apply_focus(ax, None)

    fig.canvas.mpl_connect("button_press_event", _on_click)


def plot_gantt_chart(
    solution: Schedule,
    figsize: tuple[float, float] | None = None,
    output_path: str | None = None,
    theme: ThemeName = "light",
    *,
    idle: IdleMode = "hide",
    jobs: list[Job] | None = None,
    palette: tuple[str, ...] | list[str] | None = None,
    job_colors: dict[str, str | tuple] | None = None,
    annotations: list | None = None,
    utilization: bool = True,
    interactive: bool = True,
) -> None:
    """Plot a Gantt chart from a Schedule object.

    Args:
        solution: schedule to render.
        figsize: figure size; if None, auto-sized from the number of rows
            (after `idle` filtering).
        output_path: when set, write the rendered figure here.
        theme: "light" (default) or "dark".
        idle: how to treat machines with no scheduled work. "hide" (default)
            drops them entirely; "compress" drops them but reports the count
            in the subtitle; "show" keeps all of `solution.machines`.
        jobs: optional Job objects, used to resolve readable names for the
            legend and to flag late tasks (end past `job.due_date`).
        palette: optional list of hex colors that replaces the theme's
            default categorical palette.
        job_colors: optional mapping of job id -> color, used to lock in
            specific colors for given jobs (e.g. brand colors).
        interactive: when True (default), attach hover tooltips and
            click-to-focus handlers if the matplotlib backend supports them.
    """
    if idle == "show":
        n_rows = len(solution.machines)
    else:
        n_rows = sum(
            1 for m in solution.machines if solution.mapping.get(m.id)
        )

    fig, ax = plt.subplots(figsize=figsize or _autosize(n_rows))
    fig.patch.set_facecolor(_THEMES[theme].fig_bg)
    job_color: dict[str, tuple] = _coerce_job_colors(job_colors)
    _draw_schedule_on_axes(
        ax, solution, job_color,
        theme=theme, idle=idle, jobs=jobs, palette=palette,
        annotations=annotations, utilization=utilization,
    )
    fig.tight_layout()

    if interactive:
        _attach_hover(ax)
        _attach_click_highlight(ax)

    plt.show()

    if output_path:
        cprint(
            f"Gantt chart saved to [green]{output_path}[/green]",
            style="yellow",
        )
        fig.savefig(
            output_path,
            facecolor=fig.get_facecolor(),
            dpi=160,
            bbox_inches="tight",
        )


def _coerce_job_colors(
    job_colors: dict[str, str | tuple] | None,
) -> dict[str, tuple]:
    if not job_colors:
        return {}
    out: dict[str, tuple] = {}
    for jid, c in job_colors.items():
        out[jid] = mcolors.to_rgba(c)
    return out


class LiveGanttChart:
    """Re-renders a Gantt chart in place each time a new Schedule is pushed in.

    The chart runs in matplotlib's interactive mode so ``update`` returns
    quickly without blocking the caller's loop. Job colors persist across
    updates, so a given job keeps the same color even as bars move between
    frames.

    Example:
        >>> chart = LiveGanttChart(jobs=instance.jobs)
        >>> for schedule in stream_of_schedules:
        ...     chart.update(schedule)
        >>> chart.close()
    """

    def __init__(
        self,
        figsize: tuple[float, float] = (12, 8),
        theme: ThemeName = "light",
        *,
        idle: IdleMode = "hide",
        jobs: list[Job] | None = None,
        palette: tuple[str, ...] | list[str] | None = None,
        job_colors: dict[str, str | tuple] | None = None,
        annotations: list | None = None,
        utilization: bool = True,
        interactive: bool = True,
    ) -> None:
        self._was_interactive = plt.isinteractive()
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=figsize)
        self.fig.patch.set_facecolor(_THEMES[theme].fig_bg)
        self._job_color: dict[str, tuple] = _coerce_job_colors(job_colors)
        self._theme: ThemeName = theme
        self._idle: IdleMode = idle
        self._jobs: list[Job] | None = jobs
        self._palette = palette
        self._annotations = annotations
        self._utilization = utilization
        self._interactive = interactive
        self._handlers_attached = False
        self._cursor = None

    def update(
        self,
        solution: Schedule,
        current_time: int | None = None,
        *,
        annotations: list | None = None,
    ) -> None:
        """Redraw the chart for the given schedule.

        Pass ``annotations`` to override the markers configured at construction
        time for this single update (e.g. to attach a "shift change" marker
        only on certain frames).

        Interactive state (hover cursor + click-to-focus selection) is
        preserved across updates: the focused job id lives on the axes
        (``ax._frost_focused_job``) and is re-applied to the freshly drawn
        bars; the hover cursor is disposed and rebuilt against the new
        artists.
        """
        if self._cursor is not None:
            try:
                self._cursor.remove()
            except Exception:
                # mplcursors can raise if the cursor is already gone; not fatal.
                pass
            self._cursor = None

        self.ax.clear()
        _draw_schedule_on_axes(
            self.ax, solution, self._job_color,
            current_time=current_time,
            theme=self._theme,
            idle=self._idle,
            jobs=self._jobs,
            palette=self._palette,
            annotations=annotations if annotations is not None else self._annotations,
            utilization=self._utilization,
        )

        if self._interactive:
            if not self._handlers_attached:
                # Click handler binds to the figure once; the click closure
                # reads ax.patches at click time so it always sees the
                # currently-drawn artists.
                _attach_click_highlight(self.ax)
                self._handlers_attached = True
            # Re-apply any previous focus selection to the new bars.
            focused = getattr(self.ax, "_frost_focused_job", None)
            if focused is not None:
                _apply_focus(self.ax, focused)
            # Build a fresh hover cursor for the new patch identities.
            self._cursor = _attach_hover(self.ax)

        self.fig.canvas.draw_idle()
        plt.pause(0.001)

    def close(self) -> None:
        """Close the figure and restore matplotlib's interactive mode."""
        if self._cursor is not None:
            try:
                self._cursor.remove()
            except Exception:
                pass
            self._cursor = None
        plt.close(self.fig)
        if not self._was_interactive:
            plt.ioff()


