from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.core.base import Task, Machine, Job


def test_scheduled_task_instantiation():
    """Test ScheduledTask instantiation."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    machine = Machine(id="M1", name="Machine 1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    assert scheduled_task.start_time == 0
    assert scheduled_task.end_time == 10
    assert scheduled_task.task == task
    assert scheduled_task.machine == machine


def test_schedule_instantiation():
    """Test Schedule instantiation."""
    schedule = Schedule()
    assert schedule.machines == []
    assert schedule.mapping == {}


def test_add_scheduled_task():
    """Test adding a scheduled task to the schedule."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    machine = Machine(id="M1", name="Machine 1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)

    assert machine.id in schedule.mapping
    assert scheduled_task in schedule.get_machine_tasks(machine)


def test_get_task_mapping():
    """Test getting a scheduled task mapping."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    machine = Machine(id="M1", name="Machine 1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)

    retrieved_task = schedule.get_task_mapping(task)
    assert retrieved_task == scheduled_task


def test_get_task_mapping_not_found():
    """Test getting a scheduled task mapping that does not exist."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    schedule = Schedule()

    retrieved_task = schedule.get_task_mapping(task)
    assert retrieved_task is None


def test_get_job_start_time():
    """Test getting the start time of a job."""
    task1 = Task(id="T1", name="Task 1", processing_time=5)
    task2 = Task(id="T2", name="Task 2", processing_time=7)
    machine = Machine(id="M1", name="Machine 1")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=5, task=task1, machine=machine
    )
    scheduled_task2 = ScheduledTask(
        start_time=2, end_time=9, task=task2, machine=machine
    )

    job = Job(id="J1", name="Job 1", tasks=[task1, task2])
    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)

    assert schedule.get_job_start_time(job) == 0.0


def test_get_job_start_time_no_tasks_scheduled():
    """Test getting the start time of a job with no scheduled tasks."""
    task1 = Task(id="T1", name="Task 1", processing_time=5)
    job = Job(id="J1", name="Job 1", tasks=[task1])
    schedule = Schedule()

    assert schedule.get_job_start_time(job) == 0.0


def test_get_job_end_time():
    """Test getting the end time of a job."""
    task1 = Task(id="T1", name="Task 1", processing_time=5)
    task2 = Task(id="T2", name="Task 2", processing_time=7)
    machine = Machine(id="M1", name="Machine 1")

    scheduled_task1 = ScheduledTask(
        start_time=0, end_time=5, task=task1, machine=machine
    )
    scheduled_task2 = ScheduledTask(
        start_time=2, end_time=9, task=task2, machine=machine
    )

    job = Job(id="J1", name="Job 1", tasks=[task1, task2])
    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)

    assert schedule.get_job_end_time(job) == 9.0


def test_get_job_end_time_no_tasks_scheduled():
    """Test getting the end time of a job with no scheduled tasks."""
    task1 = Task(id="T1", name="Task 1", processing_time=5)
    job = Job(id="J1", name="Job 1", tasks=[task1])
    schedule = Schedule()

    assert schedule.get_job_end_time(job) == 0.0


def test_remove_scheduled_task():
    """Test removing a scheduled task from the schedule."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    machine = Machine(id="M1", name="Machine 1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)
    assert machine.id in schedule.mapping

    schedule.remove_scheduled_task(scheduled_task)
    assert machine.id not in schedule.mapping


def test_remove_scheduled_task_not_found():
    """Test removing a scheduled task that is not in the schedule."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    machine = Machine(id="M1", name="Machine 1")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine
    )

    schedule = Schedule()
    # Do not add the task

    schedule.remove_scheduled_task(scheduled_task)
    # Should not raise an error, and mapping should remain empty
    assert schedule.mapping == {}


def test_update_scheduled_task_machine():
    """Test updating the machine for a scheduled task."""
    task = Task(id="T1", name="Task 1", processing_time=10)
    machine1 = Machine(id="M1", name="Machine 1")
    machine2 = Machine(id="M2", name="Machine 2")
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task, machine=machine1
    )

    schedule = Schedule()
    schedule.add_scheduled_task(scheduled_task)

    assert machine1.id in schedule.mapping
    assert machine2.id not in schedule.mapping
    assert scheduled_task.machine == machine1

    schedule.update_scheduled_task_machine(scheduled_task, machine2)

    assert machine1.id not in schedule.mapping
    assert machine2.id in schedule.mapping
    assert scheduled_task.machine == machine2
    assert scheduled_task in schedule.get_machine_tasks(machine2)
