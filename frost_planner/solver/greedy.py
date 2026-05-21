# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.schedule import Schedule, ScheduledTask


def _get_machine_intervals_for_task(
    task: Task,
    machine_intervals: dict[str, list[tuple[int, int]]],
    earliest_start: int,
    horizon: int,
    suitable_machines_map: dict[str, list[Machine]],
) -> dict[str, list[tuple[int, int]]]:
    """Return free intervals on each suitable machine that can host the task.

    Each returned interval is clipped to ``[earliest_start, horizon]`` and
    is wide enough to fit the task's machine-specific processing time.
    """
    s_intervals: dict[str, list[tuple[int, int]]] = {}
    suitable_machine_ids = {m.id for m in suitable_machines_map[task.id]}

    for machine_id, intervals in machine_intervals.items():
        if machine_id not in suitable_machine_ids:
            continue

        ms_intervals: list[tuple[int, int]] = []
        for start, end in intervals:
            # Intervals are sorted; nothing useful remains past horizon.
            if start >= horizon:
                break
            if end < earliest_start:
                continue
            start = max(start, earliest_start)
            end = min(end, horizon)
            processing_time = task.processing_time_on(machine_id)
            if processing_time > (end - start):
                continue
            ms_intervals.append((start, end))
        s_intervals[machine_id] = ms_intervals

    return s_intervals


def perform_task_interval_allocation(
    start_time: int,
    task: Task,
    machine: Machine,
    machine_intervals: dict[str, list[tuple[int, int]]],
) -> None:
    """Allocates a task to a machine at a specific start.

    This function updates the machine intervals to reflect the allocation of
    the task. It finds the appropriate interval for the task and splits
    it if necessary.

    Args:
        start_time (int):
            The start time for the task allocation.
        task (Task):
            The task to allocate.
        machine (Machine):
            The machine to allocate the task to.
        machine_intervals (dict[str, list[tuple[int, int]]]):
            The machine intervals to allocate the task within.

    """
    interval_idx: int = -1
    start: int = 0
    end: int = 0
    for start, end in machine_intervals[machine.id]:
        processing_time = task.processing_time_on(machine)
        if start <= start_time and end >= start_time + processing_time:
            interval_idx = machine_intervals[machine.id].index((start, end))
            break

        # Intervals are sorted, so we can break early
        if start > start_time:
            break

    if interval_idx == -1:
        raise ValueError(
            f"Cannot place task {task.id} on machine {machine.id} at "
            f"{start_time} for duration {task.processing_time_on(machine)}. "
            "No suitable "
            "interval found.",
        )

    end_time = start_time + task.processing_time_on(machine)
    if start == start_time and end == end_time:
        machine_intervals[machine.id].pop(interval_idx)
    elif start == start_time:
        machine_intervals[machine.id][interval_idx] = (end_time, end)
    elif end == end_time:
        machine_intervals[machine.id][interval_idx] = (start, start_time)
    else:
        machine_intervals[machine.id][interval_idx] = (start, start_time)
        machine_intervals[machine.id].insert(interval_idx + 1, (end_time, end))


def _allocate_task(
    start_time: int,
    task: Task,
    machine: Machine,
    machine_intervals: dict[str, list[tuple[int, int]]],
) -> ScheduledTask:
    """Place a task on a machine at ``start_time`` and return the binding."""
    perform_task_interval_allocation(
        start_time, task, machine, machine_intervals
    )
    return ScheduledTask(
        start_time=start_time,
        end_time=start_time + task.processing_time_on(machine),
        task=task,
        machine=machine,
    )


def create_schedule(
    scheduled_tasks: list[ScheduledTask],
    machines: list[Machine],
) -> Schedule:
    """Build a ``Schedule`` from already-allocated tasks and the machine set."""
    schedule = Schedule(machines=machines)
    for st in scheduled_tasks:
        schedule.add_scheduled_task(st)
    return schedule


def schedule_by_order(
    instance: SchedulingInstance,
    jobs: list[Job],
    machine_intervals: dict[str, list[tuple[int, int]]],
    *,
    horizon: int = sys.maxsize,
    initial_scheduled_tasks: dict[str, ScheduledTask] | None = None,
    min_time: int = 0,
    machine_id_map: dict[str, Machine] | None = None,
    suitable_machines_map: dict[str, list[Machine]] | None = None,
) -> list[ScheduledTask]:
    """Schedule jobs greedily by their predefined order.

    A non-optimizing solver that processes each task in instance-order
    and assigns it to the earliest feasible machine. Mutates
    ``machine_intervals`` in place; callers that need a fresh copy
    must deepcopy before calling.

    Args:
        instance:
            Scheduling instance providing machines, travel times, and
            (when ``suitable_machines_map`` is not supplied) suitable
            machines per task.
        jobs:
            Job processing order. Tasks within each job are assumed to
            be topologically sorted by their dependencies.
        machine_intervals:
            Initial availability intervals per machine. Mutated.
        horizon:
            Maximum possible end time for any task.
        initial_scheduled_tasks:
            Tasks that are already scheduled and should not be touched
            (used to seed dependency resolution).
        min_time:
            Global lower bound on start times for tasks not in
            ``initial_scheduled_tasks``.
        machine_id_map:
            Optional precomputed id→Machine map. Recomputed from
            ``instance`` if omitted.
        suitable_machines_map:
            Optional precomputed task_id→[Machine] map. Recomputed via
            ``instance.get_suitable_machines`` if omitted.

    Returns:
        Every successfully scheduled task with start/end/machine set.
    """
    if machine_id_map is None:
        machine_id_map = {m.id: m for m in instance.machines}
    if suitable_machines_map is None:
        suitable_machines_map = {
            task.id: instance.get_suitable_machines(task)
            for job in instance.jobs
            for task in job.tasks
        }
    travel_times = instance.travel_times
    scheduled_tasks: dict[str, ScheduledTask] = (
        initial_scheduled_tasks.copy() if initial_scheduled_tasks else {}
    )
    # Jobs are passed in the desired processing order; tasks within each
    # job are already topologically sorted by their dependencies.
    tasks = [task for job in jobs for task in job.tasks]

    for task in tasks:
        if task.id in scheduled_tasks:
            continue

        # Earliest start: max of caller's min_time and every predecessor's
        # end time (predecessor travel is applied per-machine below).
        min_start_time = min_time
        for dep in task.dependencies:
            min_start_time = max(min_start_time, scheduled_tasks[dep].end_time)

        selected_machine: Machine | None = None
        selected_start_time: int = sys.maxsize

        s_intervals = _get_machine_intervals_for_task(
            task,
            machine_intervals,
            min_start_time,
            horizon,
            suitable_machines_map,
        )

        for machine_id, intervals in s_intervals.items():
            for start_interval, end_interval in intervals:
                # Push the machine-available start forward past every
                # predecessor's completion (plus travel when the
                # predecessor ran on a different machine).
                adjusted_start_time = start_interval
                for dep_id in task.dependencies:
                    dep_scheduled_task = scheduled_tasks[dep_id]
                    dep_end = dep_scheduled_task.end_time
                    if dep_scheduled_task.machine.id != machine_id:
                        dep_end += travel_times.get(
                            dep_scheduled_task.machine.id, {}
                        ).get(machine_id, 0)
                    adjusted_start_time = max(adjusted_start_time, dep_end)

                duration = task.processing_time_on(machine_id)
                if adjusted_start_time + duration <= end_interval:
                    if (
                        selected_machine is None
                        or adjusted_start_time < selected_start_time
                    ):
                        selected_start_time = adjusted_start_time
                        selected_machine = machine_id_map[machine_id]
                    # First fitting slot wins on this machine; the rest
                    # would only be later.
                    break

        if selected_machine is None:
            raise ValueError(f"No suitable machine found for task: {task.id}")

        scheduled_tasks[task.id] = _allocate_task(
            start_time=selected_start_time,
            task=task,
            machine=selected_machine,
            machine_intervals=machine_intervals,
        )

    return list(scheduled_tasks.values())
