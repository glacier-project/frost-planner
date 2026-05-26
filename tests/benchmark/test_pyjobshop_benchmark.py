# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import argparse

import pytest

pytest.importorskip("pyjobshop")

from benchmarks.benchmark_solvers import (
    build_machine_intervals,
    build_pyjobshop_model,
    finite_horizon_from_intervals,
    pyjobshop_schedule_from_result,
    run_pyjobshop_solver,
)
from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.validate import validate_schedule


def _args(**overrides: object) -> argparse.Namespace:
    args: dict[str, object] = {
        "horizon": None,
        "machine_break_start": None,
        "machine_break_duration": 0,
        "machine_break_repeat": 0,
        "machine_window_horizon": None,
        "pyjobshop_time_limit": 2.0,
        "cp_sat_time_limit": 2.0,
        "pyjobshop_workers": 1,
        "cp_sat_workers": 1,
        "objective_makespan_weight": 1,
        "objective_total_flow_time_weight": 0,
        "objective_num_tardy_jobs_weight": 0,
        "objective_total_tardiness_weight": 0,
        "objective_total_earliness_weight": 0,
        "objective_max_tardiness_weight": 0,
    }
    args.update(overrides)
    return argparse.Namespace(**args)


def test_pyjobshop_benchmark_enforces_machine_dependent_travel() -> None:
    source_task = Task(
        id="T1",
        name="Source",
        processing_time=2,
        requires=["source"],
    )
    target_task = Task(
        id="T2",
        name="Target",
        processing_time=2,
        dependencies=["T1"],
        requires=["target"],
    )
    source = Machine(id="M1", name="Source", capabilities=["source"])
    slow_target = Machine(id="M2", name="Slow", capabilities=["target"])
    fast_target = Machine(id="M3", name="Fast", capabilities=["target"])
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[source_task, target_task])],
        machines=[source, slow_target, fast_target],
        travel_times={"M1": {"M2": 5, "M3": 0}},
    )

    result = run_pyjobshop_solver(instance, _args())

    assert result.solution_found
    assert result.valid_schedule
    assert result.makespan == 4
    assert result.solver_status == "OPTIMAL"


def test_pyjobshop_benchmark_converts_break_time() -> None:
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
    args = _args(
        machine_break_start=3,
        machine_break_duration=2,
        machine_window_horizon=20,
    )
    machine_intervals = build_machine_intervals(instance, args)
    horizon = finite_horizon_from_intervals(machine_intervals, args)
    model, alternatives_by_task = build_pyjobshop_model(
        instance,
        machine_intervals,
        horizon,
    )
    result = model.solve(
        solver="ortools",
        time_limit=2,
        display=False,
        num_workers=1,
    )

    schedule = pyjobshop_schedule_from_result(
        instance,
        alternatives_by_task,
        result,
    )

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.start_time == 0
    assert scheduled_task.end_time == 6
    assert scheduled_task.break_time == 2
    assert validate_schedule(schedule, instance)
