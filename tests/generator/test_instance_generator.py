# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import pytest

from frost_planner.generator.instance_generator import (
    InstanceConfiguration,
    InstanceGenerator,
)


def test_instance_generator_marks_breakable_tasks_from_configuration() -> None:
    instance = InstanceGenerator(seed=0).create_instance(
        InstanceConfiguration(
            num_jobs=3,
            min_tasks_per_job=2,
            max_tasks_per_job=2,
            num_machine_capabilities=2,
            num_machines=4,
            max_machine_capabilities_per_machine=2,
            min_processing_time=4,
            max_processing_time=5,
            min_travel_time=0,
            max_travel_time=1,
            breakable_task_ratio=1.0,
            breakable_task_min_processing_time=4,
        )
    )

    tasks = [task for job in instance.jobs for task in job.tasks]
    assert any(task.allow_breaks for task in tasks)
    assert all(task.allow_breaks for task in tasks)


def test_instance_generator_validates_breakable_task_ratio() -> None:
    with pytest.raises(ValueError, match="breakable_task_ratio"):
        InstanceGenerator(seed=0).create_instance(
            InstanceConfiguration(breakable_task_ratio=1.1)
        )


def test_instance_generator_creates_machine_specific_processing_times() -> None:
    instance = InstanceGenerator(seed=0).create_instance(
        InstanceConfiguration(
            num_jobs=2,
            min_tasks_per_job=2,
            max_tasks_per_job=2,
            num_machine_capabilities=2,
            num_machines=4,
            max_machine_capabilities_per_machine=2,
            min_processing_time=10,
            max_processing_time=10,
            min_travel_time=0,
            max_travel_time=1,
            machine_processing_time_variation=0.5,
        )
    )

    tasks = [task for job in instance.jobs for task in job.tasks]
    assert any(task.machine_processing_times for task in tasks)
    for task in tasks:
        suitable_machine_ids = {
            machine.id for machine in instance.get_suitable_machines(task)
        }
        assert set(task.machine_processing_times) == suitable_machine_ids
        assert all(
            5 <= processing_time <= 15
            for processing_time in task.machine_processing_times.values()
        )


def test_instance_generator_validates_machine_duration_variation() -> None:
    with pytest.raises(ValueError, match="machine_processing_time_variation"):
        InstanceGenerator(seed=0).create_instance(
            InstanceConfiguration(machine_processing_time_variation=1.1)
        )
