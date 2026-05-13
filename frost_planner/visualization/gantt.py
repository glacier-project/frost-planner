import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from frost_planner.core.base import TaskStatus
from frost_planner.core.schedule import Schedule
from frost_planner.utils import cprint

Y_START = 1.25
Y_DELTA = 1
BAR_WIDTH = 0.5
C_PALETTE = "Pastel1"


def _draw_schedule_on_axes(
    ax: Axes,
    solution: Schedule,
    job_color: dict[str, tuple],
    current_time: int | None = None,
) -> None:
    """Draw a Gantt-style view of `solution` onto `ax`.

    `job_color` is mutated in place: any new job id seen gets a stable color
    assigned from the palette. Pass the same dict across calls to keep colors
    consistent between redraws.

    Safe to call repeatedly on the same axes after `ax.clear()`: every piece
    of axes state this function touches is re-applied on each call.
    """
    x_max = (
        max(st.end_time for st in solution.get_tasks())
        if solution.get_tasks()
        else 100
    )
    if current_time is not None:
        x_max = max(x_max, current_time)

    y_ticks = [(i * Y_DELTA) + Y_START for i in range(len(solution.machines))]
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([m.name for m in solution.machines])
    ax.set_xlim(0, x_max)
    ax.set_xlabel("Time")
    ax.set_ylabel("Machine")
    ax.set_title("Schedule")
    ax.grid(True, linestyle="--", alpha=0.5, axis="x")

    if current_time is not None:
        ax.axvline(
            x=current_time,
            color="red",
            linestyle="--",
            linewidth=2,
            label="Current Time",
        )

    cmap = matplotlib.colormaps[C_PALETTE]

    # Map machine ID to its index for Y-axis positioning
    machine_idx = {m.id: i for i, m in enumerate(solution.machines)}

    for machine_id, tasks in solution.mapping.items():
        i = machine_idx[machine_id]
        bars = []
        colors = []
        edge_colors = []
        line_widths = []

        for t in tasks:
            # Use job_id for stable coloring
            jid = str(t.task.job_id)
            if jid not in job_color:
                job_color[jid] = cmap(len(job_color) % cmap.N)

            bars.append((t.start_time, t.task.processing_time))
            colors.append(job_color[jid])

            # Highlight tasks based on their status
            if t.task.status == TaskStatus.IN_PROGRESS:
                edge_colors.append("red")
                line_widths.append(3.0)
            elif t.task.status == TaskStatus.COMPLETED:
                edge_colors.append("green")
                line_widths.append(1.0)
            else:
                edge_colors.append("black")
                line_widths.append(1.0)

        ax.broken_barh(
            bars,
            yrange=(i + Y_START - BAR_WIDTH / 2, BAR_WIDTH),
            facecolors=colors,
            edgecolors=edge_colors,
            linewidths=line_widths,
        )

        for t in tasks:
            ax.text(
                t.start_time + t.task.processing_time / 2,
                i + Y_START,
                t.task.name,
                ha="center",
                va="center",
                fontsize=9,
            )

    # Reconstruct legend using job names if possible, or just IDs
    # Since job_color uses job_id, we'll just label them as "Job" for
    # simplicity here or we could try to find the job name if we had the
    # instance.
    patches = [
        mpatches.Patch(color=color, label=f"Job {jid[:8]}")
        for jid, color in sorted(job_color.items())
    ]
    patches.append(
        mpatches.Patch(
            facecolor="white", edgecolor="red", linewidth=2, label="Running"
        )
    )
    patches.append(
        mpatches.Patch(
            facecolor="white", edgecolor="green", linewidth=1, label="Completed"
        )
    )

    ax.legend(handles=patches, fontsize=9, loc="upper right")


def plot_gantt_chart(
    solution: Schedule,
    figsize: tuple[int, int] = (12, 8),
    output_path: str | None = None,
) -> None:
    """Plot a Gantt chart from a Schedule object.

    Args:
        solution (Schedule):
            Schedule object containing tasks with start times, durations, and
            resources.
        figsize (Tuple[int, int], optional):
            Figure size as (width, height). Defaults to (12, 8).
        output_path (str | None, optional):
            If provided, save the figure to this path. Defaults to None.

    """
    fig, ax = plt.subplots(figsize=figsize)
    _draw_schedule_on_axes(ax, solution, {})
    plt.show()

    if output_path:
        cprint(
            f"Gantt chart saved to [green]{output_path}[/green]",
            style="yellow",
        )
        fig.savefig(output_path)


class LiveGanttChart:
    """Re-renders a Gantt chart in place each time a new Schedule is pushed in.

    The chart runs in matplotlib's interactive mode so ``update`` returns
    quickly without blocking the caller's loop. Job colors persist across
    updates, so a given job keeps the same color even as bars move between
    frames.

    Example:
        >>> chart = LiveGanttChart()
        >>> for schedule in stream_of_schedules:
        ...     chart.update(schedule)
        >>> chart.close()
    """

    def __init__(self, figsize: tuple[int, int] = (12, 8)) -> None:
        self._was_interactive = plt.isinteractive()
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=figsize)
        self._job_color: dict[str, tuple] = {}

    def update(
        self, solution: Schedule, current_time: int | None = None
    ) -> None:
        """Redraw the chart for the given schedule."""
        self.ax.clear()
        _draw_schedule_on_axes(
            self.ax, solution, self._job_color, current_time=current_time
        )
        self.fig.canvas.draw_idle()
        plt.pause(0.001)

    def close(self) -> None:
        """Close the figure and restore matplotlib's interactive mode."""
        plt.close(self.fig)
        if not self._was_interactive:
            plt.ioff()
