# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""Generate hand-crafted stress benchmark instances.

The random instance generator does not naturally surface the structural
features that several CP-SAT optimizations exploit (identical machines,
identical jobs, capability bottlenecks, single-task jobs). This script
writes four fixed benchmark instances under
``benchmarks/results/fixed_instances_stress/`` so the benchmark harness
can load them via ``--instances-dir`` plus matching ``--profiles`` names.

Each filename matches ``{profile_name}_{instance_index}_seed_{seed}.json``
where ``seed`` follows the harness convention ``profile_index * 10_000``
when the four profiles are passed in alphabetical order:

* ``stress_capability_bottleneck_0_seed_0.json`` (profile_index 0)
* ``stress_identical_jobs_0_seed_10000.json``  (profile_index 1)
* ``stress_identical_machines_0_seed_20000.json``  (profile_index 2)
* ``stress_single_task_jobs_0_seed_30000.json``  (profile_index 3)

Coverage summary:

* ``stress_capability_bottleneck`` — many tasks demand a rare capability
  provided by only two machines (item #15, item #26 capability LB).
* ``stress_identical_jobs`` — twelve jobs sharing the same task signature
  (item #25 job-symmetry constraint).
* ``stress_identical_machines`` — three groups of two interchangeable
  machines with zero intra-group travel (item #11 machine-symmetry).
* ``stress_single_task_jobs`` — ten one-task jobs with diverse due dates
  (item #30 single-task job-completion fast path, only fires for
  non-makespan objectives).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from frost_planner.core.base import Job, Machine, SchedulingInstance, Task
from frost_planner.generator.instance_generator import save_instance_to_json


def _new_id() -> str:
    return str(uuid.uuid4())


def _zero_travel(
    sources: list[str], destinations: list[str]
) -> dict[str, dict[str, int]]:
    return {
        src: {dst: 0 for dst in destinations if dst != src} for src in sources
    }


def _uniform_travel(
    machines: list[Machine], value: int
) -> dict[str, dict[str, int]]:
    return {
        source.id: {
            other.id: value for other in machines if other.id != source.id
        }
        for source in machines
    }


def identical_machines_instance() -> SchedulingInstance:
    """Three identical-machine groups (2 machines each)."""
    capability_groups = [
        ("cap_alpha", "M_ALPHA"),
        ("cap_beta", "M_BETA"),
        ("cap_gamma", "M_GAMMA"),
    ]
    machines: list[Machine] = []
    group_to_machines: dict[str, list[Machine]] = {}
    for capability, prefix in capability_groups:
        group_machines = [
            Machine(
                id=f"{prefix}_{index}",
                name=f"{prefix} {index}",
                capabilities=[capability],
            )
            for index in range(2)
        ]
        machines.extend(group_machines)
        group_to_machines[capability] = group_machines

    travel = _uniform_travel(machines, value=4)
    for capability, _ in capability_groups:
        group_ids = [machine.id for machine in group_to_machines[capability]]
        for src, dst_map in _zero_travel(group_ids, group_ids).items():
            travel[src].update(dst_map)

    jobs: list[Job] = []
    for job_index in range(18):
        capability_a, _ = capability_groups[job_index % 3]
        capability_b, _ = capability_groups[(job_index + 1) % 3]
        first = Task(
            id=_new_id(),
            name=f"J{job_index}_T0",
            processing_time=6,
            requires=[capability_a],
        )
        second = Task(
            id=_new_id(),
            name=f"J{job_index}_T1",
            processing_time=5,
            requires=[capability_b],
            dependencies=[first.id],
        )
        jobs.append(
            Job(
                id=_new_id(),
                name=f"J{job_index}",
                tasks=[first, second],
                due_date=80,
            )
        )

    return SchedulingInstance(
        jobs=jobs,
        machines=machines,
        travel_times=travel,
    )


def identical_jobs_instance() -> SchedulingInstance:
    """Twelve jobs with identical task structures."""
    machines = [
        Machine(id="M0", name="M0", capabilities=["cap_x"]),
        Machine(id="M1", name="M1", capabilities=["cap_x"]),
        Machine(id="M2", name="M2", capabilities=["cap_y"]),
        Machine(id="M3", name="M3", capabilities=["cap_y"]),
    ]
    travel = _uniform_travel(machines, value=3)

    jobs: list[Job] = []
    for job_index in range(12):
        first = Task(
            id=_new_id(),
            name=f"J{job_index}_T0",
            processing_time=5,
            requires=["cap_x"],
        )
        second = Task(
            id=_new_id(),
            name=f"J{job_index}_T1",
            processing_time=7,
            requires=["cap_y"],
            dependencies=[first.id],
        )
        jobs.append(
            Job(
                id=_new_id(),
                name=f"J{job_index}",
                tasks=[first, second],
                due_date=120,
            )
        )
    return SchedulingInstance(
        jobs=jobs,
        machines=machines,
        travel_times=travel,
    )


def capability_bottleneck_instance() -> SchedulingInstance:
    """Many tasks demand a rare capability; only two machines provide it."""
    machines = [
        Machine(id="RARE_A", name="Rare A", capabilities=["cap_rare"]),
        Machine(id="RARE_B", name="Rare B", capabilities=["cap_rare"]),
    ] + [
        Machine(
            id=f"COMMON_{index}",
            name=f"Common {index}",
            capabilities=["cap_common"],
        )
        for index in range(8)
    ]
    travel = _uniform_travel(machines, value=2)

    jobs: list[Job] = []
    for job_index in range(20):
        rare_task = Task(
            id=_new_id(),
            name=f"J{job_index}_rare",
            processing_time=4,
            requires=["cap_rare"],
        )
        warmup_task = Task(
            id=_new_id(),
            name=f"J{job_index}_warmup",
            processing_time=3,
            requires=["cap_common"],
        )
        finish_task = Task(
            id=_new_id(),
            name=f"J{job_index}_finish",
            processing_time=3,
            requires=["cap_common"],
            dependencies=[rare_task.id],
        )
        jobs.append(
            Job(
                id=_new_id(),
                name=f"J{job_index}",
                tasks=[warmup_task, rare_task, finish_task],
                due_date=60,
            )
        )
    return SchedulingInstance(
        jobs=jobs,
        machines=machines,
        travel_times=travel,
    )


def single_task_jobs_instance() -> SchedulingInstance:
    """Ten one-task jobs with mixed capabilities and tight due dates.

    Exercises item #30's job-completion fast path (single task → reuse
    task end as the completion var, skipping ``AddMaxEquality``). The
    diverse durations and due dates ensure the heuristic incumbents
    differ between orderings, so non-makespan scenarios produce real
    tardiness/flow signals rather than trivial zero objectives.
    """
    machines = [
        Machine(id=f"S_{index}", name=f"S{index}", capabilities=["cap_s"])
        for index in range(2)
    ] + [
        Machine(id=f"T_{index}", name=f"T{index}", capabilities=["cap_t"])
        for index in range(2)
    ] + [
        Machine(id="U_0", name="U0", capabilities=["cap_u"]),
    ]
    travel = _uniform_travel(machines, value=2)

    # (capability, processing_time, due_date)
    job_specs: list[tuple[str, int, int]] = [
        ("cap_s", 6, 8),
        ("cap_t", 4, 10),
        ("cap_s", 5, 14),
        ("cap_t", 7, 12),
        ("cap_u", 9, 11),
        ("cap_s", 3, 6),
        ("cap_t", 8, 22),
        ("cap_u", 5, 9),
        ("cap_s", 7, 18),
        ("cap_t", 6, 16),
    ]
    jobs: list[Job] = []
    for job_index, (capability, processing_time, due_date) in enumerate(
        job_specs
    ):
        task = Task(
            id=_new_id(),
            name=f"J{job_index}_T0",
            processing_time=processing_time,
            requires=[capability],
        )
        jobs.append(
            Job(
                id=_new_id(),
                name=f"J{job_index}",
                tasks=[task],
                due_date=due_date,
            )
        )
    return SchedulingInstance(
        jobs=jobs,
        machines=machines,
        travel_times=travel,
    )


def main() -> None:
    """Generate four stress instances under the fixed_instances_stress dir."""
    output_directory = Path("benchmarks/results/fixed_instances_stress")
    output_directory.mkdir(parents=True, exist_ok=True)

    # Filenames must match the benchmark harness's instance_path_for()
    # convention: ``{profile_name}_{instance_index}_seed_{seed}.json``
    # with seed = ``args.seed (0) + profile_index * 10_000 + instance_index``
    # when the four profiles are listed in alphabetical order.
    instances: list[tuple[str, int, SchedulingInstance]] = [
        ("stress_capability_bottleneck", 0, capability_bottleneck_instance()),
        ("stress_identical_jobs", 10_000, identical_jobs_instance()),
        ("stress_identical_machines", 20_000, identical_machines_instance()),
        ("stress_single_task_jobs", 30_000, single_task_jobs_instance()),
    ]
    for profile_name, seed, instance in instances:
        path = output_directory / f"{profile_name}_0_seed_{seed}.json"
        save_instance_to_json(instance, str(path))
        print(
            f"Wrote {path} "
            f"(jobs={len(instance.jobs)}, "
            f"tasks={sum(len(job.tasks) for job in instance.jobs)}, "
            f"machines={len(instance.machines)})"
        )


if __name__ == "__main__":
    main()
