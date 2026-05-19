# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import pytest

pytest.importorskip("ortools.sat.python.cp_model")

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.core.objective import ObjectiveWeights
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


def test_cp_sat_solver_pairwise_travel_model_enforces_travel_time() -> None:
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

    schedule = CpSatSolver(
        instance=instance,
        horizon=10,
        use_travel_table=False,
    ).schedule()

    scheduled_task_1 = schedule.get_task_mapping(task_1)
    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_1 is not None
    assert scheduled_task_2 is not None
    assert scheduled_task_2.start_time >= scheduled_task_1.end_time + 3
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_pairwise_compressed_travel_enforces_extra_time() -> None:
    task_1 = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["source"],
    )
    task_2 = Task(
        id="T2",
        name="Task 2",
        processing_time=2,
        dependencies=["T1"],
        requires=["target"],
    )
    source = Machine(
        id="M1",
        name="Source",
        capabilities=["source"],
    )
    late_target = Machine(
        id="M2",
        name="Late Target",
        capabilities=["target"],
    )
    early_target = Machine(
        id="M3",
        name="Early Target",
        capabilities=["target"],
    )
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task_1, task_2])],
        machines=[source, late_target, early_target],
        travel_times={
            "M1": {
                "M2": 0,
                "M3": 5,
            }
        },
    )
    solver = CpSatSolver(
        instance=instance,
        horizon=30,
        machine_intervals={
            "M1": [(0, 30)],
            "M2": [(20, 30)],
            "M3": [(0, 30)],
        },
        travel_model="pairwise",
    )
    locked_task = ScheduledTask(
        start_time=0,
        end_time=2,
        task=task_1,
        machine=source,
    )
    solver.lock_tasks(locked_task)

    schedule = solver.schedule()

    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_2 is not None
    assert scheduled_task_2.machine == early_target
    assert scheduled_task_2.start_time >= locked_task.end_time + 5
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_hybrid_travel_model_enforces_travel_time() -> None:
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

    schedule = CpSatSolver(
        instance=instance,
        horizon=10,
        travel_model="hybrid",
    ).schedule()

    scheduled_task_1 = schedule.get_task_mapping(task_1)
    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_1 is not None
    assert scheduled_task_2 is not None
    assert scheduled_task_2.start_time >= scheduled_task_1.end_time + 3
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_optional_bound_formulations_schedule() -> None:
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

    schedule = CpSatSolver(
        instance=instance,
        horizon=10,
        use_dependency_bounds=True,
        use_machine_load_bounds=True,
    ).schedule()

    scheduled_task_1 = schedule.get_task_mapping(task_1)
    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_1 is not None
    assert scheduled_task_2 is not None
    assert scheduled_task_2.start_time >= scheduled_task_1.end_time
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_heuristic_hints_schedule() -> None:
    task_1 = Task(id="T1", name="Task 1", processing_time=2)
    task_2 = Task(
        id="T2",
        name="Task 2",
        processing_time=3,
        dependencies=["T1"],
    )
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task_1, task_2])],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=10,
        use_heuristic_hints=True,
    ).schedule()

    scheduled_task_1 = schedule.get_task_mapping(task_1)
    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_1 is not None
    assert scheduled_task_2 is not None
    assert scheduled_task_2.start_time >= scheduled_task_1.end_time
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_minimizes_tardy_jobs_objective() -> None:
    urgent = Task(id="T1", name="Urgent", processing_time=5)
    relaxed = Task(id="T2", name="Relaxed", processing_time=5)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[
            Job(id="J1", name="Urgent Job", tasks=[urgent], due_date=5),
            Job(id="J2", name="Relaxed Job", tasks=[relaxed], due_date=100),
        ],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=20,
        objective=ObjectiveWeights(makespan=0, num_tardy_jobs=1),
    ).schedule()

    urgent_scheduled = schedule.get_task_mapping(urgent)
    assert urgent_scheduled is not None
    assert urgent_scheduled.end_time <= 5
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_minimizes_due_date_deviation() -> None:
    task = Task(id="T1", name="Task 1", processing_time=2)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task], due_date=10)],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=20,
        objective=ObjectiveWeights(
            makespan=0,
            total_tardiness=1,
            total_earliness=1,
        ),
    ).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.end_time == 10
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


def test_cp_sat_solver_skips_machine_that_cannot_fit_task() -> None:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=4,
        requires=["work"],
    )
    short_machine = Machine(
        id="M1",
        name="Short Machine",
        capabilities=["work"],
    )
    feasible_machine = Machine(
        id="M2",
        name="Feasible Machine",
        capabilities=["work"],
    )
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[short_machine, feasible_machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=10,
        machine_intervals={
            "M1": [(0, 3), (5, 7)],
            "M2": [(0, 10)],
        },
    ).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.machine == feasible_machine


def test_cp_sat_solver_uses_machine_specific_processing_time() -> None:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=8,
        machine_processing_times={
            "M1": 8,
            "M2": 3,
        },
    )
    slow_machine = Machine(id="M1", name="Slow")
    fast_machine = Machine(id="M2", name="Fast")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[slow_machine, fast_machine],
    )

    schedule = CpSatSolver(instance=instance, horizon=20).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.machine == fast_machine
    assert scheduled_task.start_time == 0
    assert scheduled_task.end_time == 3
    assert validate_schedule(schedule, instance)


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

    with pytest.raises(
        ValueError,
        match=r"(No feasible machine alternative|infeasible)",
    ):
        CpSatSolver(instance=instance, horizon=3).schedule()


def test_cp_sat_solver_single_machine_uses_machine_specific_duration() -> None:
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=8,
        machine_processing_times={"M1": 5},
    )
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    schedule = CpSatSolver(instance=instance, horizon=10).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.machine == machine
    assert scheduled_task.start_time == 0
    assert scheduled_task.end_time == 5
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_single_machine_breakable_with_dependency() -> None:
    task_1 = Task(id="T1", name="Task 1", processing_time=2)
    task_2 = Task(
        id="T2",
        name="Task 2",
        processing_time=4,
        dependencies=["T1"],
        allow_breaks=True,
    )
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task_1, task_2])],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=12,
        machine_intervals={"M1": [(0, 2), (3, 6), (8, 12)]},
    ).schedule()

    scheduled_task_1 = schedule.get_task_mapping(task_1)
    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_1 is not None
    assert scheduled_task_2 is not None
    assert scheduled_task_1.start_time == 0
    assert scheduled_task_1.end_time == 2
    assert scheduled_task_2.start_time >= scheduled_task_1.end_time
    assert (
        scheduled_task_2.end_time - scheduled_task_2.start_time
        - scheduled_task_2.break_time
        == 4
    )
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_mixes_single_and_multi_alternative_tasks() -> None:
    fixed_task = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["welding"],
    )
    flexible_task = Task(
        id="T2",
        name="Task 2",
        processing_time=3,
        dependencies=["T1"],
        requires=["work"],
    )
    welding = Machine(
        id="M1",
        name="Welding",
        capabilities=["welding", "work"],
    )
    other = Machine(
        id="M2",
        name="Other",
        capabilities=["work"],
    )
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[fixed_task, flexible_task])],
        machines=[welding, other],
        travel_times={"M1": {"M2": 4}, "M2": {"M1": 4}},
    )

    schedule = CpSatSolver(instance=instance, horizon=15).schedule()

    scheduled_fixed = schedule.get_task_mapping(fixed_task)
    scheduled_flexible = schedule.get_task_mapping(flexible_task)
    assert scheduled_fixed is not None
    assert scheduled_flexible is not None
    assert scheduled_fixed.machine == welding
    assert scheduled_flexible.machine in {welding, other}
    if scheduled_flexible.machine == other:
        assert scheduled_flexible.start_time >= scheduled_fixed.end_time + 4
    else:
        assert scheduled_flexible.start_time >= scheduled_fixed.end_time
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_non_breakable_start_pruning_skips_short() -> None:
    task = Task(id="T1", name="Task 1", processing_time=4)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=20,
        machine_intervals={"M1": [(0, 2), (5, 7), (10, 20)]},
    ).schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.start_time == 10
    assert scheduled_task.end_time == 14
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_minimizes_max_tardiness_only() -> None:
    urgent = Task(id="T1", name="Urgent", processing_time=3)
    relaxed = Task(id="T2", name="Relaxed", processing_time=3)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[
            Job(id="J1", name="Urgent Job", tasks=[urgent], due_date=4),
            Job(id="J2", name="Relaxed Job", tasks=[relaxed], due_date=20),
        ],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=20,
        objective=ObjectiveWeights(makespan=0, max_tardiness=1),
    ).schedule()

    urgent_scheduled = schedule.get_task_mapping(urgent)
    assert urgent_scheduled is not None
    assert urgent_scheduled.end_time <= 4
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_minimizes_total_flow_time_only() -> None:
    short = Task(id="T1", name="Short", processing_time=2)
    long = Task(id="T2", name="Long", processing_time=5)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[
            Job(id="J1", name="Short Job", tasks=[short]),
            Job(id="J2", name="Long Job", tasks=[long]),
        ],
        machines=[machine],
    )

    schedule = CpSatSolver(
        instance=instance,
        horizon=20,
        objective=ObjectiveWeights(makespan=0, total_flow_time=1),
    ).schedule()

    short_scheduled = schedule.get_task_mapping(short)
    long_scheduled = schedule.get_task_mapping(long)
    assert short_scheduled is not None
    assert long_scheduled is not None
    assert short_scheduled.end_time < long_scheduled.end_time
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_warm_start_reuses_previous_schedule() -> None:
    task_1 = Task(id="T1", name="Task 1", processing_time=3)
    task_2 = Task(
        id="T2", name="Task 2", processing_time=2, dependencies=["T1"]
    )
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task_1, task_2])],
        machines=[machine],
    )
    solver = CpSatSolver(instance=instance, horizon=20)

    first = solver.schedule()
    cached = solver._last_scheduled_tasks
    assert cached is not None
    assert len(cached) == 2
    assert validate_schedule(first, instance)

    second = solver.schedule()
    assert validate_schedule(second, instance)
    first_task_2 = first.get_task_mapping(task_2)
    second_task_2 = second.get_task_mapping(task_2)
    assert first_task_2 is not None
    assert second_task_2 is not None
    assert first_task_2.end_time == second_task_2.end_time


def test_cp_sat_solver_locked_pred_single_machine_successor() -> None:
    task_1 = Task(
        id="T1",
        name="Task 1",
        processing_time=2,
        requires=["cutting"],
    )
    task_2 = Task(
        id="T2",
        name="Task 2",
        processing_time=3,
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
        travel_times={"M1": {"M2": 2}},
    )
    solver = CpSatSolver(instance=instance, horizon=15)
    locked_task = ScheduledTask(
        start_time=0,
        end_time=2,
        task=task_1,
        machine=cutting,
    )
    solver.lock_tasks(locked_task)

    schedule = solver.schedule()

    scheduled_task_2 = schedule.get_task_mapping(task_2)
    assert scheduled_task_2 is not None
    assert scheduled_task_2.machine == welding
    assert scheduled_task_2.start_time == 4
    assert scheduled_task_2.end_time == 7


def test_cp_sat_solver_pruned_machines_tighten_processing_bounds() -> None:
    """When pruning is on, min processing time reflects only feasible machines.

    Fast machine has only a 1-time-unit window — too short for the task's
    fast-machine duration (2). With pruning the fast machine is removed, so
    _min_processing_time falls back to the slow machine's duration (5).
    """
    task = Task(
        id="T1",
        name="Task 1",
        processing_time=5,
        machine_processing_times={"M_FAST": 2, "M_SLOW": 5},
    )
    fast_machine = Machine(id="M_FAST", name="Fast")
    slow_machine = Machine(id="M_SLOW", name="Slow")
    instance = SchedulingInstance(
        jobs=[Job(id="J1", name="Job 1", tasks=[task])],
        machines=[fast_machine, slow_machine],
    )

    solver = CpSatSolver(
        instance=instance,
        horizon=20,
        machine_intervals={"M_FAST": [(0, 1)], "M_SLOW": [(0, 20)]},
        prune_infeasible_alternatives=True,
    )
    schedule = solver.schedule()

    scheduled_task = schedule.get_task_mapping(task)
    assert scheduled_task is not None
    assert scheduled_task.machine == slow_machine
    assert scheduled_task.end_time - scheduled_task.start_time == 5
    assert validate_schedule(schedule, instance)
    # After solve, the cache must reflect only the slow machine.
    assert solver._feasible_machines_cache is not None
    assert solver._feasible_machines_cache["T1"] == [slow_machine]
    # And _min_processing_time consults the pruned set.
    assert solver._min_processing_time(task) == 5
    assert validate_schedule(schedule, instance)


def test_cp_sat_solver_objective_hint_path_keeps_correctness() -> None:
    """Non-makespan objective hints should not regress correctness."""
    urgent = Task(id="T1", name="Urgent", processing_time=3)
    relaxed = Task(id="T2", name="Relaxed", processing_time=3)
    on_time = Task(id="T3", name="On Time", processing_time=3)
    machine = Machine(id="M1", name="Machine 1")
    instance = SchedulingInstance(
        jobs=[
            Job(id="J1", name="Urgent Job", tasks=[urgent], due_date=4),
            Job(id="J2", name="Relaxed Job", tasks=[relaxed], due_date=15),
            Job(id="J3", name="On-time Job", tasks=[on_time], due_date=9),
        ],
        machines=[machine],
    )
    schedule = CpSatSolver(
        instance=instance,
        horizon=30,
        objective=ObjectiveWeights(
            makespan=1,
            total_tardiness=2,
            max_tardiness=5,
            total_earliness=1,
            num_tardy_jobs=3,
        ),
    ).schedule()
    assert validate_schedule(schedule, instance)
    urgent_scheduled = schedule.get_task_mapping(urgent)
    assert urgent_scheduled is not None
    # Urgent job must finish on or before its due date (4).
    assert urgent_scheduled.end_time <= 4


def test_cp_sat_solver_capability_cumulative_packs_bottleneck() -> None:
    """Three tasks requiring a 2-machine capability cannot all overlap."""
    rare_caps = ["rare"]
    rare1 = Machine(id="R1", name="Rare 1", capabilities=rare_caps)
    rare2 = Machine(id="R2", name="Rare 2", capabilities=rare_caps)
    instance = SchedulingInstance(
        jobs=[
            Job(
                id=f"J{i}",
                name=f"Job {i}",
                tasks=[
                    Task(
                        id=f"T{i}",
                        name=f"Task {i}",
                        processing_time=5,
                        requires=rare_caps,
                    )
                ],
            )
            for i in range(3)
        ],
        machines=[rare1, rare2],
    )
    schedule = CpSatSolver(instance=instance, horizon=30).schedule()
    assert validate_schedule(schedule, instance)
    # With only 2 rare-capability machines and 3 tasks, total makespan is
    # at least ceil(3 * 5 / 2) = 8.
    end_times = [
        schedule.get_task_mapping(task).end_time
        for job in instance.jobs
        for task in job.tasks
        if schedule.get_task_mapping(task) is not None
    ]
    assert max(end_times) >= 8
