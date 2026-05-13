# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import pytest

pytest.importorskip("ortools.sat.python.cp_model")

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.schedule import ScheduledTask
from frost_planner.core.validate import validate_schedule
from frost_planner.solver.cp_sat_solver import CpSatSolver


def test_cp_sat_solver_schedules_single_task() -> None:
    task = Task(id="T1", name="Task 1", processing_time=2)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    schedule = CpSatSolver(instance=instance, horizon=10).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.start_time == 0
    assert scheduled_task.end_time == 2
    assert scheduled_task.machine == machine
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_respects_capabilities() -> None:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["welding"],
    )
    cutting = Machine(
        id="M1",
        name="Cutting",
        capabilities=["cutting"],
    )
    welding = Machine(
        id="M2",
        name="Welding",
        capabilities=["welding"],
    )
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[cutting, welding],
    )

    schedule = CpSatSolver(instance=instance, horizon=10).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.machine == welding
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_enforces_dependency_travel_time() -> None:
    task_1 = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["cutting"],
    )
    task_2 = Task(
        id="T2",
        name="Task 2",
        processing_time=2,
        dependencies=["T1"],
        requires=["welding"],
    )
    cutting = Machine(
        id="M1",
        name="Cutting",
        capabilities=["cutting"],
    )
    welding = Machine(
        id="M2",
        name="Welding",
        capabilities=["welding"],
    )
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task_1, task_2])],
        machines=[cutting, welding],
        travel_times={"M1": {"M2": 3}},
    )

    schedule = CpSatSolver(instance=instance, horizon=10).schedule()

    scheduled_task_1 = schedule.get_task_mapping(task_1)
    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_1 is not None
    assert scheduled_task_2 is not None
    assert scheduled_task_2.start_time >= scheduled_task_1.end_time + 3
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_raises_on_missing_travel_time() -> None:
    task_1 = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["cutting"],
    )
    task_2 = Task(
        id="T2",
        name="Task 2",
        processing_time=2,
        dependencies=["T1"],
        requires=["welding"],
    )
    cutting = Machine(
        id="M1",
        name="Cutting",
        capabilities=["cutting"],
    )
    welding = Machine(
        id="M2",
        name="Welding",
        capabilities=["welding"],
    )
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task_1, task_2])],
        machines=[cutting, welding],
    )

    with pytest.raises(ValueError, match="No travel times defined"):
        CpSatSolver(instance=instance, horizon=10).schedule()


def test_cp_sat_solver_non_breakable_task_avoids_unavailable_window() -> None:
    task = Task(id="T1", name="Task 1", processing_time=4)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=10,
        machine_intervals={"M1": [(0, 3), (5, 10)]},
    ).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.start_time == 5
    assert scheduled_task.end_time == 9
    assert scheduled_task.break_time == 0


def test_cp_sat_solver_breakable_task_spans_unavailable_window() -> None:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=4,
        allow_breaks=True,
    )
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=10,
        machine_intervals={"M1": [(0, 3), (5, 10)]},
    ).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.start_time == 0
    assert scheduled_task.end_time == 6
    assert scheduled_task.break_time == 2


def test_cp_sat_solver_respects_locked_predecessor() -> None:
    task_1 = Task(id="T1", name="Task 1", processing_time=2)
    task_2 = Task(
        id="T2",
        name="Task 2",
        processing_time=2,
        dependencies=["T1"],
    )
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task_1, task_2])],
        machines=[machine],
    )
    solver = CpSatSolver(instance=instance, horizon=10)
    locked_task = ScheduledTask(
        start_time=0,
        end_time=2,
        task=task_1,
        machine=machine,
    )
    solver.lock_tasks(locked_task)

    schedule = solver.schedule()

    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_2 is not None
    assert schedule.get_task_mapping(task_1) == locked_task
    assert scheduled_task_2.start_time == 2
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_raises_when_no_machine_is_suitable() -> None:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["welding"],
    )
    machine = Machine(
        id="M1",
        name="Machine 1",
        capabilities=["cutting"],
    )
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    with pytest.raises(ValueError, match="No suitable machine"):
        CpSatSolver(instance=instance, horizon=10).schedule()


def test_cp_sat_solver_raises_when_horizon_is_infeasible() -> None:
    task = Task(id="T1", name="Task 1", processing_time=4)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    with pytest.raises(ValueError, match="CP-SAT did not find"):
        CpSatSolver(instance=instance, horizon=3).schedule()
