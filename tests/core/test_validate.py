from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.core.validate import (
    _validate_all_instance_tasks_scheduled,
    _validate_machine_assignments,
    _validate_machine_capabilities,
    _validate_machine_task_overlaps,
    _validate_scheduled_task_times,
    _validate_task_dependencies,
    validate_schedule,
)


# Fixtures for common objects
@pytest.fixture
def sample_task() -> Task:
    return Task(id="T1", name="Task 1", processing_time=10)


@pytest.fixture
def sample_machine() -> Machine:
    return Machine(id="M1", name="Machine 1", capabilities=["cutting"])


@pytest.fixture
def mock_cerror() -> Any:
    with patch("frost_planner.core.validate.cerror") as mock:
        yield mock


@pytest.fixture
def sample_scheduled_task(
    sample_task: Task,
    sample_machine: Machine,
) -> ScheduledTask:
    return ScheduledTask(
        start_time=0, end_time=10, task=sample_task, machine=sample_machine
    )


@pytest.fixture
def sample_schedule(
    sample_scheduled_task: ScheduledTask,
    sample_machine: Machine,
) -> Schedule:
    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(sample_scheduled_task)
    return schedule


@pytest.fixture
def sample_job(sample_task: Task) -> Job:
    return Job(id="J1", name="Job 1", tasks=[sample_task])


@pytest.fixture
def sample_instance(
    sample_job: Job,
    sample_machine: Machine,
) -> SchedulingInstance:
    return SchedulingInstance(jobs=[sample_job], machines=[sample_machine])


# Tests for _validate_scheduled_task_times
def test_validate_scheduled_task_times_valid(
    sample_scheduled_task: ScheduledTask,
) -> None:
    assert _validate_scheduled_task_times(sample_scheduled_task) is True


def test_scheduled_task_constructor_negative_start_time(
    sample_task: Task,
    sample_machine: Machine,
) -> None:
    with pytest.raises(ValidationError):
        ScheduledTask(
            start_time=-1,
            end_time=10,
            task=sample_task,
            machine=sample_machine,
        )


def test_scheduled_task_constructor_negative_end_time(
    sample_task: Task,
    sample_machine: Machine,
) -> None:
    with pytest.raises(ValidationError):
        ScheduledTask(
            start_time=0,
            end_time=-1,
            task=sample_task,
            machine=sample_machine,
        )


def test_scheduled_task_constructor_start_end_mismatch(
    sample_task: Task,
    sample_machine: Machine,
) -> None:
    with pytest.raises(ValueError):
        ScheduledTask(
            start_time=10,
            end_time=5,
            task=sample_task,
            machine=sample_machine,
        )


def test_validate_scheduled_task_times_duration_mismatch(
    sample_task: Task,
    sample_machine: Machine,
) -> None:
    with pytest.raises(ValidationError):
        ScheduledTask(
            start_time=0,
            end_time=5,
            task=sample_task,
            machine=sample_machine,
        )


# Tests for _validate_machine_assignments
def test_validate_machine_assignments_valid(
    sample_schedule: Schedule,
) -> None:
    assert _validate_machine_assignments(sample_schedule) is True


# Tests for _validate_machine_task_overlaps
def test_validate_machine_task_overlaps_valid(
    sample_task: Task,
    sample_machine: Machine,
) -> None:
    scheduled_task1 = ScheduledTask(
        start_time=0,
        end_time=10,
        task=sample_task,
        machine=sample_machine,
    )
    scheduled_task2 = ScheduledTask(
        start_time=10,
        end_time=20,
        task=sample_task,
        machine=sample_machine,
    )
    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)
    assert _validate_machine_task_overlaps(schedule) is True


def test_validate_machine_task_overlaps_invalid(
    sample_task: Task,
    sample_machine: Machine,
    mock_cerror: Any,
) -> None:
    scheduled_task1 = ScheduledTask(
        start_time=0,
        end_time=10,
        task=sample_task,
        machine=sample_machine,
    )
    scheduled_task2 = ScheduledTask(
        start_time=5,
        end_time=15,
        task=sample_task,
        machine=sample_machine,
    )
    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(scheduled_task1)
    schedule.add_scheduled_task(scheduled_task2)

    assert _validate_machine_task_overlaps(schedule) is False
    mock_cerror.assert_called()


# Tests for _validate_all_instance_tasks_scheduled
def test_validate_all_instance_tasks_scheduled_valid(
    sample_schedule: Schedule,
    sample_instance: SchedulingInstance,
) -> None:
    assert (
        _validate_all_instance_tasks_scheduled(sample_schedule, sample_instance) is True
    )


def test_validate_all_instance_tasks_scheduled_missing_task(
    sample_schedule: Schedule,
    sample_job: Job,
    sample_machine: Machine,
    mock_cerror: Any,
) -> None:
    task_missing = Task(id="T_missing", name="Missing Task", processing_time=5)
    instance = SchedulingInstance(
        jobs=[sample_job, Job(id="J_new", name="Job New", tasks=[task_missing])],
        machines=[sample_machine],
    )
    assert _validate_all_instance_tasks_scheduled(sample_schedule, instance) is False
    mock_cerror.assert_called()


def test_validate_all_instance_tasks_scheduled_extra_task(
    sample_scheduled_task: ScheduledTask,
    sample_machine: Machine,
    sample_job: Job,
    mock_cerror: Any,
) -> None:
    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(sample_scheduled_task)

    task_extra = Task(id="T_extra", name="Extra Task", processing_time=5)
    machine_extra = Machine(id="M_extra", name="Machine Extra")
    scheduled_task_extra = ScheduledTask(
        start_time=0, end_time=5, task=task_extra, machine=machine_extra
    )
    schedule.add_scheduled_task(scheduled_task_extra)

    instance = SchedulingInstance(jobs=[sample_job], machines=[sample_machine])
    assert _validate_all_instance_tasks_scheduled(schedule, instance) is False
    mock_cerror.assert_called()


# Tests for _validate_machine_capabilities
def test_validate_machine_capabilities_valid(
    sample_scheduled_task: ScheduledTask,
    sample_machine: Machine,
) -> None:
    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(sample_scheduled_task)

    assert _validate_machine_capabilities(schedule) is True


def test_validate_machine_capabilities_valid_with_requirements(
    sample_machine: Machine,
) -> None:
    task_req = Task(
        id="T_req", name="Task Req", processing_time=10, requires=["cutting"]
    )
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task_req, machine=sample_machine
    )
    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(scheduled_task)
    assert _validate_machine_capabilities(schedule) is True


def test_validate_machine_capabilities_invalid(
    sample_machine: Machine,
    mock_cerror: Any,
) -> None:
    task_req = Task(
        id="T_req", name="Task Req", processing_time=10, requires=["welding"]
    )
    scheduled_task = ScheduledTask(
        start_time=0, end_time=10, task=task_req, machine=sample_machine
    )
    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(scheduled_task)
    assert _validate_machine_capabilities(schedule) is False
    mock_cerror.assert_called()


# Tests for _validate_task_dependencies
def test_validate_task_dependencies_valid(sample_machine: Machine) -> None:
    task_a = Task(id="T_A", name="Task A", processing_time=5)
    task_b = Task(id="T_B", name="Task B", processing_time=5, dependencies=["T_A"])

    scheduled_task_a = ScheduledTask(
        start_time=0, end_time=5, task=task_a, machine=sample_machine
    )
    scheduled_task_b = ScheduledTask(
        start_time=5, end_time=10, task=task_b, machine=sample_machine
    )

    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(scheduled_task_a)
    schedule.add_scheduled_task(scheduled_task_b)

    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="J1", tasks=[task_a, task_b])],
        machines=[sample_machine],
    )
    assert _validate_task_dependencies(schedule, instance) is True


def test_validate_task_dependencies_invalid_order(
    sample_machine: Machine,
    mock_cerror: Any,
) -> None:
    task_a = Task(id="T_A", name="Task A", processing_time=5)
    task_b = Task(id="T_B", name="Task B", processing_time=5, dependencies=["T_A"])

    scheduled_task_a = ScheduledTask(
        start_time=5, end_time=10, task=task_a, machine=sample_machine
    )
    scheduled_task_b = ScheduledTask(
        start_time=0, end_time=5, task=task_b, machine=sample_machine
    )  # B starts before A ends

    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(scheduled_task_a)
    schedule.add_scheduled_task(scheduled_task_b)

    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="J1", tasks=[task_a, task_b])],
        machines=[sample_machine],
    )
    assert _validate_task_dependencies(schedule, instance) is False
    mock_cerror.assert_called()


def test_validate_task_dependencies_missing_dependent_task(
    sample_machine: Machine,
    mock_cerror: Any,
) -> None:
    task_a = Task(id="T_A", name="Task A", processing_time=5)
    task_b = Task(id="T_B", name="Task B", processing_time=5, dependencies=["T_A"])

    scheduled_task_b = ScheduledTask(
        start_time=0, end_time=5, task=task_b, machine=sample_machine
    )

    schedule = Schedule(machines=[sample_machine])
    schedule.add_scheduled_task(scheduled_task_b)

    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="J1", tasks=[task_a, task_b])],
        machines=[sample_machine],
    )
    assert _validate_task_dependencies(schedule, instance) is False
    mock_cerror.assert_called()


def test_validate_task_dependencies_travel_time_violation(
    sample_task: Task,
    sample_machine: Machine,
    mock_cerror: Any,
) -> None:
    machine2 = Machine(id="M2", name="Machine 2")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="J1", tasks=[sample_task])],
        machines=[sample_machine, machine2],
        travel_times={sample_machine.id: {machine2.id: 5}},  # 5 units travel time
    )
    task_a = Task(id="T_A", name="Task A", processing_time=5)
    task_b = Task(id="T_B", name="Task B", processing_time=5, dependencies=["T_A"])

    scheduled_task_a = ScheduledTask(
        start_time=0, end_time=5, task=task_a, machine=sample_machine
    )
    scheduled_task_b = ScheduledTask(
        start_time=6, end_time=11, task=task_b, machine=machine2
    )  # Starts at 6, but needs 5+5=10

    schedule = Schedule(machines=[sample_machine, machine2])
    schedule.add_scheduled_task(scheduled_task_a)
    schedule.add_scheduled_task(scheduled_task_b)

    assert _validate_task_dependencies(schedule, instance) is False
    mock_cerror.assert_called()


# Tests for validate_schedule (integration)
def test_validate_schedule_valid(
    sample_schedule: Schedule,
    sample_instance: SchedulingInstance,
) -> None:
    assert validate_schedule(sample_schedule, sample_instance) is True
