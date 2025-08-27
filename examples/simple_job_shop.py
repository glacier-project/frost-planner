import argparse
from frost_sheet.core.base import SchedulingInstance
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.solver.stochastic_solver import StochasticSolver
from frost_sheet.visualization.gantt import plot_gantt_chart


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate random job-shop scheduling instances"
    )
    parser.add_argument(
        "--instance",
        type=str,
        default="resources/instances/easy/instance_0.json",
        help="Instance configuration to use",
    )
    parser.add_argument(
        "--solver",
        type=str,
        default="dummy",
        choices=["dummy", "stochastic"],
        help="Solver to use for scheduling",
    )
    return parser.parse_args()


def load_instance(file_path: str) -> SchedulingInstance:
    with open(file_path, "r") as f:
        return SchedulingInstance.model_validate_json(f.read())


def main():
    args = parse_args()
    instance = load_instance(args.instance)

    machines = instance.machines
    jobs = instance.jobs

    machine_dict = {m.machine_id: m for m in machines}

    print("Loaded Scheduling Instance:")
    print(f"|--># Machines: {len(machines)}")
    print(f"|--># Jobs: {len(jobs)}")

    if args.solver == "dummy":
        solver = DummySolver(
            instance=instance,
        )
    else:
        solver = StochasticSolver(
            instance=instance,
        )

    schedule = solver.schedule()

    print("Generated Schedule:")
    for job in jobs:
        print(f"|--> Job {job.name} schedule:")
        for task in job.tasks:
            for m, tasks in schedule.machine_schedule.items():
                for t in tasks:
                    if t.task == task:
                        print(
                            f"  |--> Task {task.name} starts at {t.start_time} and ends at {t.end_time} on Machine {machine_dict[m].name}"
                        )

    plot_gantt_chart(schedule)


if __name__ == "__main__":
    main()
