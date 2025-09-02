import sys
from frost_sheet.core.base import Job, Machine, Task
from frost_sheet.core.schedule import ScheduledTask, Schedule
from typing import Dict


def _get_machine_intervals_for_task(
    task: Task,
    machine_intervals: dict[str, list[tuple[int, int]]],
    earliest_start: int,
    horizon: int,
) -> dict[str, list[tuple[int, int]]]:
    """Gets the time intervals for a task on a specific machine.

    Args:
        task (Task): The task to get intervals for.
        machine_intervals (dict[str, list[tuple[int, int]]]): The machine intervals to get intervals from.
        earliest_start (int): The earliest start time for the task based on its dependencies.
        horizon (int): The time horizon for the scheduling.
    Returns:
        dict[str, list[tuple[int, int]]]: A dictionary mapping machine IDs to their available time intervals for the task.
    """

    s_intervals = {}

    for machine_id, intervals in machine_intervals.items():
        if machine_id not in task.machines:
            continue

        task_start_time = task.start_time if task.start_time else 0
        task_start_time = max(task_start_time, earliest_start)
        task_end_time = task.end_time if task.end_time else horizon
        ms_intervals = []

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


def _allocate_task(
    start_time: int,
    task: Task,
    machine_id: str,
    machine_intervals: dict[str, list[tuple[int, int]]],
) -> ScheduledTask:
    # find the selected interval
    interval_idx: int = -1
    start: int = 0
    end: int = 0
    for start, end in machine_intervals[machine_id]:
        if start <= start_time and end >= start_time + task.processing_time:
            interval_idx = machine_intervals[machine_id].index((start, end))
            break

    # if the interval is exactly the same as the task's time, remove it
    end_time = start_time + task.processing_time
    if start == start_time and end == end_time:
        machine_intervals[machine_id].pop(interval_idx)

    # if the start of the interval is equal to the task's start time, reduce its length
    elif start == start_time:
        machine_intervals[machine_id][interval_idx] = (end_time, end)

    # if the end of the interval is equal to the task's end time, reduce its length
    elif end == end_time:
        machine_intervals[machine_id][interval_idx] = (start, start_time)

    # if the task is contained within the interval, split the interval
    else:
        machine_intervals[machine_id][interval_idx] = (start, start_time)
        machine_intervals[machine_id].insert(interval_idx + 1, (end_time, end))

    return ScheduledTask(
        start_time=start_time,
        end_time=start_time + task.processing_time,
        task=task,
        machine_id=machine_id,
    )


def _create_schedule(
    scheduled_tasks: list[ScheduledTask], machines: list[Machine]
) -> Schedule:
    """Creates a schedule from the list of scheduled tasks and available machines.

    Args:
        scheduled_tasks (list[ScheduledTask]): The list of scheduled tasks.
        machines (list[Machine]): The list of available machines.

    Returns:
        Schedule: The schedule created from the scheduled tasks and machines.
    """
    schedule = {
        machine.machine_id: [
            task for task in scheduled_tasks if task.machine_id == machine.machine_id
        ]
        for machine in machines
    }
    return Schedule(machines=machines, schedule=schedule)


def _schedule_by_order(
    jobs: list[Job],
    machines: list[Machine],
    machine_intervals: dict[str, list[tuple[int, int]]],
    horizon: int,
    travel_times: Dict[str, Dict[str, int]],
) -> list[ScheduledTask]:
    """
    Schedules jobs based on their predefined order and machine availability.
    This is a greedy, non-optimizing solver that processes tasks sequentially.

    Args:
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
            if start_time > min_start_time:
                min_start_time = start_time

        # Initialize variables to track the best machine and its corresponding
        # start time for the current task.
        # - 'selected_machine_id' will store the ID of the machine chosen for
        #   this task.
        # - 'selected_start_time' will store the earliest time this task can
        #   start on 'selected_machine_id'. Initialize with a very large integer
        #   to easily find the minimum.
        selected_machine_id: str = ""
        selected_start_time: int = sys.maxsize

        # Find available time intervals for the task on suitable machines. This
        # considers the task's requirements and the machines' capabilities, as
        # well as the task's earliest possible start time (min_start_time).
        s_intervals = _get_machine_intervals_for_task(
            task, machine_intervals, min_start_time, horizon
        )

        # Iterate through each suitable machine and its available intervals to
        # find the best fit.
        for machine_id, intervals in s_intervals.items():
            if not intervals:
                # If no intervals are available for this machine, skip it.
                continue

            # The earliest time this task could start on the current
            # 'machine_id' based solely on the machine's availability.
            current_machine_earliest_start = intervals[0][0]

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
                if dep_scheduled_task.machine_id != machine_id:
                    # Retrieve the travel time from the source machine
                    # (dependency's machine) to the destination machine (current
                    # 'machine_id'). Default to 0 if no specific travel time is
                    # defined for the pair.
                    travel_time = travel_times.get(
                        dep_scheduled_task.machine_id, {}
                    ).get(machine_id, 0)
                    # The task cannot start until the dependent task finishes
                    # AND the piece has traveled to the current machine.
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

            # Compare this 'adjusted_start_time' with the best found so far. We
            # want to find the machine that allows the task to start earliest.
            if not selected_machine_id or adjusted_start_time < selected_start_time:
                selected_start_time = adjusted_start_time
                selected_machine_id = machine_id

        # After checking all suitable machines, ensure a machine was found. If
        # not, it means the task cannot be scheduled within the given horizon or
        # constraints.
        assert (
            selected_machine_id != ""
        ), f"No suitable machine found for task: {task.task_id}"

        # Allocate the task to the selected machine with its determined start
        # time. This also updates the machine's availability intervals.
        scheduled_task = _allocate_task(
            start_time=selected_start_time,
            task=task,
            machine_id=selected_machine_id,
            machine_intervals=machine_intervals,
        )
        # Add the newly scheduled task to our record.
        scheduled_tasks[task.task_id] = scheduled_task

    # Return the list of all successfully scheduled tasks.
    return list(scheduled_tasks.values())
