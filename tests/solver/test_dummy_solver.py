# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import pytest

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.metrics import calculate_start_time
from frost_planner.generator.instance_generator import (
    InstanceConfiguration,
    InstanceGenerator,
)
from frost_planner.solver.dummy_solver import DummySolver


@pytest.mark.parametrize(
    "instance",
    [
        InstanceGenerator().create_instance(
            configuration=InstanceConfiguration()
        )
        for _ in range(3)
    ],
)
class TestDummySolver:
    def test_schedule(self, instance: SchedulingInstance) -> None:
        solver = DummySolver(instance=instance)

        schedule = solver.schedule()

        assert schedule is not None

    @pytest.mark.parametrize("start_time", [0, 5, 10])
    def test_schedule_from(
        self, instance: SchedulingInstance, start_time: int
    ) -> None:
        solver = DummySolver(instance=instance)

        schedule = solver.schedule(start_time=start_time)

        assert schedule is not None
        assert calculate_start_time(schedule) == start_time


def test_dummy_solver_uses_machine_specific_processing_time() -> None:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=5,
        machine_processing_times={"M1": 7},
    )
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    schedule = DummySolver(instance=instance).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.end_time == 7
