import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from frost_planner.core.schedule import Schedule
from frost_planner.utils import cprint

Y_START = 1.25
Y_DELTA = 1
BAR_WIDTH = 0.5
C_PALETTE = "Pastel1"


def plot_gantt_chart(
    solution: Schedule,
    figsize: tuple[int, int] = (12, 8),
    output_path: str | None = None,
) -> None:
    """
    Plot a Gantt chart from a Schedule object.

    Args:
        solution (Schedule):
            Schedule object containing tasks with start times, durations, and
            resources.
        figsize (Tuple[int, int], optional):
            Figure size as (width, height). Defaults to (12, 8).

    """
    _, ax = plt.subplots(figsize=figsize)

    x_max = max([st.end_time for st in solution.get_tasks()])
    y_ticks = [(i * Y_DELTA) + Y_START for i in range(len(solution.machines))]
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([m.name for m in solution.machines])
    ax.set_xlim(0, x_max)
    ax.set_xlabel("Time")
    ax.set_ylabel("Machine")
    ax.set_title("Schedule")
    ax.grid(True, linestyle="--", alpha=0.5, axis="x")

    # colors
    cmap = matplotlib.colormaps[C_PALETTE]
    job_color = {}

    for i, (machine, tasks) in enumerate(solution.mapping.items()):
        bars = []
        colors = []

        for t in tasks:
            job_id = int(t.task.name[-3:-2])
            if job_id not in job_color:
                job_color[job_id] = cmap(job_id)
            bars.append((t.start_time, t.task.processing_time))
            colors.append(job_color[job_id])

        ax.broken_barh(
            bars,
            yrange=(i + Y_START - BAR_WIDTH / 2, BAR_WIDTH),
            facecolors=colors,
            edgecolors="black",
        )

        # add task_id on bars
        for j, t in enumerate(tasks):
            job_id = int(t.task.name[-3:-2])
            task_id = t.task.name[-1]
            ax.text(
                t.start_time + t.task.processing_time / 2,
                i + Y_START,
                f"T{job_id}_{task_id}",
                ha="center",
                va="center",
            )

    # create legend
    patches = [
        mpatches.Patch(color=color, label=f"Job {job_id}")
        for job_id, color in sorted(job_color.items())
    ]
    ax.legend(handles=patches, fontsize=11, loc="upper right")

    plt.show()

    if output_path:
        cprint(
            f"Gantt chart saved to [green]{output_path}[/green]",
            style="yellow",
        )
        plt.savefig(output_path)
