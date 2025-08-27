from frost_sheet.core.base import Job, Machine, Task
from frost_sheet.core.schedule import ScheduledTask, Schedule


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
    interval_idx = -1
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
    machine_schedule = {
        machine.machine_id: [
            task for task in scheduled_tasks if task.machine_id == machine.machine_id
        ]
        for machine in machines
    }
    return Schedule(machines=machines, machine_schedule=machine_schedule)


def _schedule_by_order(
    jobs: list[Job],
    machines: list[Machine],
    machine_intervals: dict[str, list[tuple[int, int]]],
    horizon: int,
) -> list[ScheduledTask]:
    """Schedules jobs based on their order and machine availability.

    Args:
        jobs (list[Job]): The list of jobs to schedule.
        machines (list[Machine]): The list of available machines.
        machine_intervals (dict[str, list[tuple[int, int]]]): The machine intervals to use for scheduling.
        horizon (int): The time horizon for the scheduling.

    Returns:
        list[ScheduledTask]: The list of scheduled tasks.
    """

    scheduled_tasks: dict[str, ScheduledTask] = {}

    tasks = [task for job in jobs for task in job.tasks]
    for task in tasks:
        min_start_time = 0
        for dep in task.dependencies:
            start_time = scheduled_tasks[dep].end_time
            if start_time > min_start_time:
                min_start_time = start_time

        s_intervals = _get_machine_intervals_for_task(
            task, machine_intervals, min_start_time, horizon
        )

        machine_id = ""

        for machine_id, intervals in s_intervals.items():
            if not intervals:
                continue

            # take the earliest starting interval
            start_time = intervals[0][0]
            curr_start_time = s_intervals[machine_id][0][0]
            if not machine_id or curr_start_time > start_time:
                machine_id = machine_id

        assert machine_id != "", f"No suitable machine found for task: {task.task_id}"

        scheduled_task = _allocate_task(
            start_time=start_time,
            task=task,
            machine_id=machine_id,
            machine_intervals=machine_intervals,
        )
        scheduled_tasks[task.task_id] = scheduled_task

    return list(scheduled_tasks.values())
