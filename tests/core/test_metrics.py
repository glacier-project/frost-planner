from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.metrics import (
    calculate_lateness,
    calculate_makespan,
    calculate_num_tardy_jobs,
    calculate_tardiness,
    calculate_total_flow_time,
)
from frost_planner.core.schedule import Schedule, ScheduledTask


def test_calculate_makespan_empty_schedule() -> None:
    """Test makespan calculation for an empty schedule."""
    schedule = Schedule()
    assert calculate_makespan(schedule) == 0.0


def test_calculate_makespan_single_task() -> None:
    """Test makespan calculation for a schedule with a single task."""
    task = Task(id="T1", name="T1", processing_time=10)
    machine = Machine(id="M1", name="M1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)

    assert calculate_makespan(schedule) == 10.0


def test_calculate_makespan_multiple_tasks_same_machine() -> None:
    """Test makespan calculation for multiple tasks on the same machine."""
    task1 = Task(id="T1", name="T1", processing_time=5)
    task2 = Task(id="T2", name="T2", processing_time=7)
    machine = Machine(id="M1", name="M1")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=5, task=task1, machine=machine
    )
    scheduled_task2 = ScheduledTask(
        start_time=5, end_time=12, task=task2, machine=machine
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)

    assert calculate_makespan(schedule) == 12.0


def test_calculate_makespan_multiple_tasks_different_machines() -> None:
    """Test makespan calculation for multiple tasks on different machines."""
    task1 = Task(id="T1", name="T1", processing_time=5)
    task2 = Task(id="T2", name="T2", processing_time=7)
    machine1 = Machine(id="M1", name="M1")
    machine2 = Machine(id="M2", name="M2")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=5, task=task1, machine=machine1
    )
    scheduled_task2 = ScheduledTask(
        start_time=2, end_time=9, task=task2, machine=machine2
    )  # Ends later

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)

    assert calculate_makespan(schedule) == 9.0


def test_calculate_makespan_complex_scenario() -> None:
    """
    Test makespan calculation for a more complex scenario with multiple machines
    and tasks.
    """
    task1 = Task(id="T1", name="T1", processing_time=10)
    task2 = Task(id="T2", name="T2", processing_time=5)
    task3 = Task(id="T3", name="T3", processing_time=8)
    task4 = Task(id="T4", name="T4", processing_time=3)

    machine1 = Machine(id="M1", name="M1")
    machine2 = Machine(id="M2", name="M2")
    machine3 = Machine(id="M3", name="M3")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=10, task=task1, machine=machine1
    )
    scheduled_task2 = ScheduledTask(
        start_time=10, end_time=15, task=task2, machine=machine1
    )  # M1 ends at 15
    scheduled_task3 = ScheduledTask(
        start_time=5, end_time=13, task=task3, machine=machine2
    )  # M2 ends at 13
    scheduled_task4 = ScheduledTask(
        start_time=12, end_time=15, task=task4, machine=machine3
    )  # M3 ends at 15

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)
    schedule.add_scheduled_task(scheduled_task3)
    schedule.add_scheduled_task(scheduled_task4)

    # The latest end time is 15.0 (from task2 and task4)
    assert calculate_makespan(schedule) == 15.0


def test_calculate_total_flow_time_empty_schedule() -> None:
    """Test total flow time calculation for an empty schedule."""
    schedule = Schedule()
    assert calculate_total_flow_time(schedule) == 0.0


def test_calculate_total_flow_time_single_task() -> None:
    """Test total flow time calculation for a schedule with a single task."""
    task = Task(id="T1", name="T1", processing_time=10)
    machine = Machine(id="M1", name="M1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)

    assert calculate_total_flow_time(schedule) == 10.0


def test_calculate_total_flow_time_multiple_tasks() -> None:
    """Test total flow time calculation for multiple tasks on different machines."""
    task1 = Task(id="T1", name="T1", processing_time=5)
    task2 = Task(id="T2", name="T2", processing_time=7)
    task3 = Task(id="T3", name="T3", processing_time=3)

    machine1 = Machine(id="M1", name="M1")
    machine2 = Machine(id="M2", name="M2")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=5, task=task1, machine=machine1
    )
    scheduled_task2 = ScheduledTask(
        start_time=0, end_time=7, task=task2, machine=machine2
    )
    scheduled_task3 = ScheduledTask(
        start_time=5, end_time=8, task=task3, machine=machine1
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)
    schedule.add_scheduled_task(scheduled_task3)

    # Flow time = (5 + 7 + 8) = 20
    assert calculate_total_flow_time(schedule) == 20.0


def test_calculate_lateness_no_due_date() -> None:
    """Test lateness calculation when jobs have no due dates."""
    task = Task(id="T1", name="T1", processing_time=10)
    machine = Machine(id="M1", name="M1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    job = Job(id="J1", name="J1", tasks=[task], due_date=None)
    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)
    instance = SchedulingInstance(jobs=[job], machines=[machine])

    assert calculate_lateness(schedule, instance) == {}


def test_calculate_lateness_on_time_job() -> None:
    """Test lateness calculation for a job that finishes on time."""
    task = Task(id="T1", name="T1", processing_time=10)
    machine = Machine(id="M1", name="M1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    job = Job(id="J1", name="J1", tasks=[task], due_date=10)
    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)
    instance = SchedulingInstance(jobs=[job], machines=[machine])

    assert calculate_lateness(schedule, instance) == {"J1": 0.0}


def test_calculate_lateness_late_job() -> None:
    """Test lateness calculation for a job that finishes late."""
    task = Task(id="T1", name="T1", processing_time=10)
    machine = Machine(id="M1", name="M1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    job = Job(id="J1", name="J1", tasks=[task], due_date=8)
    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)
    instance = SchedulingInstance(jobs=[job], machines=[machine])

    assert calculate_lateness(schedule, instance) == {"J1": 2.0}


def test_calculate_tardiness_on_time_job() -> None:
    """Test tardiness calculation for a job that finishes on time."""
    task = Task(id="T1", name="T1", processing_time=10)
    machine = Machine(id="M1", name="M1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    job = Job(id="J1", name="J1", tasks=[task], due_date=10)
    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)
    instance = SchedulingInstance(jobs=[job], machines=[machine])

    assert calculate_tardiness(schedule, instance) == {"J1": 0.0}


def test_calculate_tardiness_late_job() -> None:
    """Test tardiness calculation for a job that finishes late."""
    task = Task(id="T1", name="T1", processing_time=10)
    machine = Machine(id="M1", name="M1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    job = Job(id="J1", name="J1", tasks=[task], due_date=8)
    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)
    instance = SchedulingInstance(jobs=[job], machines=[machine])

    assert calculate_tardiness(schedule, instance) == {"J1": 2.0}


def test_calculate_num_tardy_jobs_no_tardy() -> None:
    """Test number of tardy jobs when all jobs are on time."""
    task1 = Task(id="T1", name="T1", processing_time=10)
    task2 = Task(id="T2", name="T2", processing_time=5)
    machine = Machine(id="M1", name="M1")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=10, task=task1, machine=machine
    )
    scheduled_task2 = ScheduledTask(
        start_time=10, end_time=15, task=task2, machine=machine
    )

    job1 = Job(id="J1", name="J1", tasks=[task1], due_date=10)
    job2 = Job(id="J2", name="J2", tasks=[task2], due_date=15)

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)
    instance = SchedulingInstance(jobs=[job1, job2], machines=[machine])

    assert calculate_num_tardy_jobs(schedule, instance) == 0


def test_calculate_num_tardy_jobs_some_tardy() -> None:
    """Test number of tardy jobs when some jobs are late."""
    task1 = Task(id="T1", name="T1", processing_time=10)
    task2 = Task(id="T2", name="T2", processing_time=5)
    machine = Machine(id="M1", name="M1")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=10, task=task1, machine=machine
    )
    scheduled_task2 = ScheduledTask(
        start_time=10, end_time=15, task=task2, machine=machine
    )

    job1 = Job(id="J1", name="J1", tasks=[task1], due_date=8)  # Late
    job2 = Job(id="J2", name="J2", tasks=[task2], due_date=15)  # On time

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)
    instance = SchedulingInstance(jobs=[job1, job2], machines=[machine])

    assert calculate_num_tardy_jobs(schedule, instance) == 1


def test_calculate_num_tardy_jobs_all_tardy() -> None:
    """Test number of tardy jobs when all jobs are late."""
    task1 = Task(id="T1", name="T1", processing_time=10)
    task2 = Task(id="T2", name="T2", processing_time=5)
    machine = Machine(id="M1", name="M1")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=10, task=task1, machine=machine
    )
    scheduled_task2 = ScheduledTask(
        start_time=10, end_time=15, task=task2, machine=machine
    )

    job1 = Job(id="J1", name="J1", tasks=[task1], due_date=8)  # Late
    job2 = Job(id="J2", name="J2", tasks=[task2], due_date=12)  # Late

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)
    instance = SchedulingInstance(jobs=[job1, job2], machines=[machine])

    assert calculate_num_tardy_jobs(schedule, instance) == 2
