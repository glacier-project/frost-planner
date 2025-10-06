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
    """
    Gets the time intervals for a task on a specific machine.

    Args:
        task (Task):
            The task to get intervals for.
        machine_intervals (dict[str, list[tuple[int, int]]]):
            The machine intervals to get intervals from.
        earliest_start (int):
            The earliest start time for the task based on its dependencies.
        horizon (int):
            The time horizon for the scheduling.
        suitable_machines_map (dict[str, list[Machine]]):
            A mapping of task IDs to their suitable machines.

    Returns:
        dict[str, list[tuple[int, int]]]:
            A dictionary mapping machine IDs to their available time intervals
            for the task.

    """
    s_intervals: dict[str, list[tuple[int, int]]] = {}

    # Get suitable machines for the task.
    suitable_machines = suitable_machines_map[task.id]
    # Convert to set for efficient lookup.
    suitable_machine_ids = {m.id for m in suitable_machines}

    for machine_id, intervals in machine_intervals.items():
        if machine_id not in suitable_machine_ids:
            continue

        # Task start_time and end_time are no longer attributes of Task
        # definition. Use earliest_start and horizon for interval calculations.
        task_start_time = earliest_start
        task_end_time = horizon
        ms_intervals: list[tuple[int, int]] = []

        # adds all the intervals that can fit the task
        for start, end in intervals:
            # exit if the next intervals starts after the task's end time
            if start >= task_end_time:
                break

            # skip if the interval ends before the task's start time
            if end < task_start_time:
                continue

            # earliest start time
            start = max(start, task_start_time)
            # latest end time
            end = min(end, task_end_time)

            # check if the task can fit in the interval
            if task.processing_time > (end - start):
                continue

            ms_intervals.append((start, end))
        s_intervals[machine_id] = ms_intervals

    return s_intervals


def _perform_task_interval_allocation(
    start_time: int,
    task: Task,
    machine: Machine,
    machine_intervals: dict[str, list[tuple[int, int]]],
) -> None:
    """
    Performs the actual modification of machine intervals based on task allocation.

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
        if start <= start_time and end >= start_time + task.processing_time:
            interval_idx = machine_intervals[machine.id].index((start, end))
            break

        # Intervals are sorted, so we can break early
        if start > start_time:
            break

    if interval_idx == -1:
        raise ValueError(
            f"Cannot place task {task.id} on machine {machine.id} at {start_time} "
            f"for duration {task.processing_time}. No suitable interval found.",
        )

    end_time = start_time + task.processing_time
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
    """
    Allocates a task to a machine at a specific start time.

    Args:
        start_time (int):
            The start time for the task allocation.
        task (Task):
            The task to allocate.
        machine (Machine):
            The machine to allocate the task to.
        machine_intervals (dict[str, list[tuple[int, int]]]):
            The machine intervals to allocate the task within.

    Returns:
        ScheduledTask:
            The scheduled task allocation.

    """
    _perform_task_interval_allocation(start_time, task, machine, machine_intervals)
    return ScheduledTask(
        start_time=start_time,
        end_time=start_time + task.processing_time,
        task=task,
        machine=machine,
    )


def _create_schedule(
    scheduled_tasks: list[ScheduledTask],
    machines: list[Machine],
) -> Schedule:
    """
    Creates a schedule from the list of scheduled tasks and available machines.

    Args:
        scheduled_tasks (list[ScheduledTask]):
            The list of scheduled tasks.
        machines (list[Machine]):
            The list of available machines.

    Returns:
        Schedule:
            The schedule created from the scheduled tasks and machines.

    """
    schedule = Schedule(machines=machines)
    for st in scheduled_tasks:
        schedule.add_scheduled_task(st)
    return schedule


def _schedule_by_order(
    instance: SchedulingInstance,
    jobs: list[Job],
    machines: list[Machine],
    machine_intervals: dict[str, list[tuple[int, int]]],
    horizon: int,
    travel_times: dict[str, dict[str, int]],
    machine_id_map: dict[str, Machine],
    suitable_machines_map: dict[str, list[Machine]],
) -> list[ScheduledTask]:
    """
    Schedules jobs based on their predefined order and machine availability.
    This is a greedy, non-optimizing solver that processes tasks sequentially.

    Args:
        instance (SchedulingInstance):
            The scheduling instance containing jobs and machines.
        jobs (list[Job]):
            The list of jobs to schedule. Tasks within each job are assumed to
            be topologically sorted by their dependencies.
        machines (list[Machine]):
            The list of available machines.
        machine_intervals (dict[str, list[tuple[int, int]]]):
            Initial availability intervals for each machine.
        horizon (int):
            The time horizon for the scheduling, defining the maximum possible
            end time for any task.
        travel_times (Dict[str, Dict[str, int]]):
            A dictionary representing the time taken to move a piece from a
            source machine to a destination machine.
        machine_id_map (dict[str, Machine]):
            A mapping of machine IDs to their corresponding Machine objects.
        suitable_machines_map (dict[str, list[Machine]]):
            A mapping of task IDs to their suitable machines.

    Returns:
        list[ScheduledTask]:
            A list of tasks that have been successfully scheduled, each with a
            determined start time, end time, and assigned machine.

    """
    # Dictionary to store already scheduled tasks, keyed by their task_id. This
    # allows for quick lookup of dependency completion times.
    scheduled_tasks: dict[str, ScheduledTask] = {}

    # Flatten the list of jobs into a single list of tasks. Tasks are processed
    # in the order they appear, which is assumed to be a valid topological order
    # within each job.
    tasks = [task for job in jobs for task in job.tasks]

    # Iterate through each task to schedule it.
    for task in tasks:
        # Determine the earliest possible start time for the current task based
        # on its dependencies. A task cannot start until all its direct
        # predecessors are completed.
        min_start_time = 0
        for dep in task.dependencies:
            # The task can only start after its dependency has finished. We take
            # the maximum end time among all dependencies.
            start_time = scheduled_tasks[dep].end_time
            min_start_time = max(min_start_time, start_time)

        # Initialize variables to track the best machine and its corresponding
        # start time for the current task.
        # - 'selected_machine' will store the machine chosen for this task.
        # - 'selected_start_time' will store the earliest time this task can
        #   start on 'selected_machine'. Initialize with a very large integer
        #   to easily find the minimum.
        selected_machine: Machine | None = None
        selected_start_time: int = sys.maxsize

        # Find available time intervals for the task on suitable machines. This
        # considers the task's requirements and the machines' capabilities, as
        # well as the task's earliest possible start time (min_start_time).
        s_intervals = _get_machine_intervals_for_task(
            task, machine_intervals, min_start_time, horizon, suitable_machines_map
        )

        # Iterate through each suitable machine and its available intervals to
        # find the best fit.
        for machine_id, intervals in s_intervals.items():
            if not intervals:
                # If no intervals are available for this machine, skip it.
                continue

            for start_interval, end_interval in intervals:
                # The earliest time this task could start on the current
                # 'machine_id' based solely on the machine's availability.
                current_machine_earliest_start = start_interval

                # Calculate the adjusted start time, considering both machine
                # availability and the completion of dependencies, including travel
                # time if applicable.
                adjusted_start_time = current_machine_earliest_start

                # Account for travel time from predecessor tasks if they are on
                # different machines.
                for dep_id in task.dependencies:
                    dep_scheduled_task = scheduled_tasks[dep_id]

                    # If the dependent task was processed on a different machine
                    # than the current 'machine_id' being considered for the current
                    # task, then a travel time delay must be added.
                    if dep_scheduled_task.machine.id != machine_id:
                        travel_time = travel_times.get(
                            dep_scheduled_task.machine.id, {}
                        ).get(machine_id, 0)
                        adjusted_start_time = max(
                            adjusted_start_time,
                            dep_scheduled_task.end_time + travel_time,
                        )
                    else:
                        # If the dependent task is on the same machine, no travel
                        # time is incurred.
                        adjusted_start_time = max(
                            adjusted_start_time,
                            dep_scheduled_task.end_time,
                        )

                # Check if the task, with its adjusted start time, still fits within
                # the current interval.
                if adjusted_start_time + task.processing_time <= end_interval:
                    # If it fits, this is a potential candidate.
                    if (
                        not selected_machine
                        or adjusted_start_time < selected_start_time
                    ):
                        selected_start_time = adjusted_start_time
                        selected_machine = machine_id_map[machine_id]
                    # We found a valid slot in this interval, no need to check
                    # further intervals for this machine.
                    break  # Move to the next machine

        # After checking all suitable machines, ensure a machine was found. If
        # not, it means the task cannot be scheduled within the given horizon or
        # constraints.
        if not selected_machine:
            raise ValueError(f"No suitable machine found for task: {task.id}")

        # Allocate the task to the selected machine with its determined start
        # time. This also updates the machine's availability intervals.
        scheduled_task = _allocate_task(
            start_time=selected_start_time,
            task=task,
            machine=selected_machine,
            machine_intervals=machine_intervals,
        )
        # Add the newly scheduled task to our record.
        scheduled_tasks[task.id] = scheduled_task

    # Return the list of all successfully scheduled tasks.
    return list(scheduled_tasks.values())
