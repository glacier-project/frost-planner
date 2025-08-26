from datetime import datetime, timedelta
import matplotlib
import pandas as pd
from typing import Optional, List, Tuple, Dict, Any

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from frost_sheet.core.schedule import Schedule, ScheduledTask

Y_START = 1.25
Y_DELTA = 1
BAR_WIDTH = 0.5
C_PALETTE = "Pastel1"

def plot_gantt_chart(schedule: Schedule, 
                    figsize: Tuple[int, int] = (12, 8)) -> None:
    """
    Plot a Gantt chart from a Schedule object.
    
    Args:
        schedule: Schedule object containing tasks with start times, durations, and resources
        figsize: Figure size as (width, height)
    """
    fig, ax = plt.subplots(figsize=figsize)

    x_max = max([t.end_time for s in schedule.machine_schedule.values() for t in s])
    y_ticks = [(i * Y_DELTA) + Y_START for i in range(len(schedule.machines))]
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([m.name for m in schedule.machines])
    ax.set_xlim(0, x_max)
    ax.set_xlabel('Time')
    ax.set_ylabel('Machine')
    ax.grid(True, linestyle='--', alpha=0.5, axis='x')

    # colors 
    cmap = matplotlib.colormaps[C_PALETTE]
    job_color = {}

    for i, (m, tasks) in enumerate(schedule.machine_schedule.items()):
        bars = []
        colors = []

        for t in tasks:
            job_id = int(t.task.name[-3:-2])
            if job_id not in job_color:
                job_color[job_id] = cmap(job_id)
            bars.append((t.start_time, t.task.processing_time))
            colors.append(job_color[job_id])

        ax.broken_barh(bars, yrange=(i+Y_START-BAR_WIDTH/2, BAR_WIDTH), facecolors=colors, edgecolors='black')

        # add task_id on bars
        for j, t in enumerate(tasks):
            job_id = int(t.task.name[-3:-2])
            task_id = t.task.name[-1]
            ax.text(t.start_time + t.task.processing_time / 2, i + Y_START, f'T{job_id}_{task_id}', ha='center', va='center')

    # create legend
    patches =[
        mpatches.Patch(color=color, label=f'Job {job_id}')
        for job_id, color in sorted(job_color.items())
    ]
    ax.legend(handles=patches, fontsize=11)

    plt.show()



