from frost_sheet.core.base import SchedulingInstance
from frost_sheet.core.schedule import Schedule


def calculate_start_time(schedule: Schedule) -> float:
    """
    Calculates the start time of a given schedule.

    Args:
        schedule (Schedule):
            The schedule to evaluate.

    Returns:
        float:
            The start time (earliest start time of all tasks).

    """
    all_start_times = []
    for st in schedule.get_tasks():
        all_start_times.append(st.start_time)
    if not all_start_times:
        return 0.0
    return min(all_start_times)

def calculate_makespan(schedule: Schedule) -> float:
    """
    Calculates the makespan of a given schedule.

    Args:
        schedule (Schedule):
            The schedule to evaluate.

    Returns:
        float:
            The makespan (completion time of the last task).

    """
    all_end_times = []
    for st in schedule.get_tasks():
        all_end_times.append(st.end_time)
    if not all_end_times:
        return 0.0
    return max(all_end_times)


def calculate_total_flow_time(schedule: Schedule) -> float:
    """
    Calculates the total flow time of a given schedule.

    Args:
        schedule (Schedule):
            The schedule to evaluate.

    Returns:
        float:
            The total flow time (sum of completion times of all tasks).

    """
    total_flow_time = 0.0
    for st in schedule.get_tasks():
        total_flow_time += st.end_time
    return total_flow_time


def calculate_lateness(
    schedule: Schedule,
    instance: SchedulingInstance,
) -> dict[str, float]:
    """
    Calculates the lateness for each job in the schedule.

    Args:
        schedule (Schedule):
            The schedule to evaluate.
        instance (SchedulingInstance):
            The scheduling instance with job due dates.

    Returns:
        dict[str, float]:
            A dictionary mapping job names to their lateness.

    """
    lateness_by_job = {}
    for job in instance.jobs:
        if job.due_date is not None:
            job_completion_time = schedule.get_job_end_time(job)
            lateness = float(job_completion_time - job.due_date)
            lateness_by_job[job.name] = lateness
    return lateness_by_job


def calculate_tardiness(
    schedule: Schedule,
    instance: SchedulingInstance,
) -> dict[str, float]:
    """
    Calculates the tardiness for each job in the schedule.

    Args:
        schedule (Schedule):
            The schedule to evaluate.
        instance (SchedulingInstance):
            The scheduling instance with job due dates.

    Returns:
        dict[str, float]:
            A dictionary mapping job names to their tardiness.

    """
    tardiness_by_job = {}
    lateness_by_job = calculate_lateness(schedule, instance)
    for job_name, lateness in lateness_by_job.items():
        tardiness_by_job[job_name] = float(max(0.0, lateness))
    return tardiness_by_job


def calculate_num_tardy_jobs(
    schedule: Schedule,
    instance: SchedulingInstance,
) -> int:
    """
    Calculates the number of tardy jobs in the schedule. A job is considered
    tardy if its completion time exceeds its due date.

    Args:
        schedule (Schedule):
            The schedule to evaluate.
        instance (SchedulingInstance):
            The scheduling instance with job due dates.

    Returns:
        int:
            The number of tardy jobs.

    """
    tardy_jobs_count = 0
    for job in instance.jobs:
        if job.due_date is not None:
            job_completion_time = schedule.get_job_end_time(job)
            if job_completion_time > job.due_date:
                tardy_jobs_count += 1
    return tardy_jobs_count
