import argparse
from frost_sheet.core.schedule import Schedule, ScheduledTask, validate_schedule
from frost_sheet.core.base import Machine, SchedulingInstance
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.solver.stochastic_solver import StochasticSolver
from frost_sheet.visualization.gantt import plot_gantt_chart
from frost_sheet.utils import cprint, cerror


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate random job-shop scheduling instances"
    )
    parser.add_argument(
        "-i",
        "--instance",
        type=str,
        default="resources/instances/easy/instance_0.json",
        help="Instance configuration to use",
    )
    parser.add_argument(
        "-s",
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


def scheduled_task_to_str(st: ScheduledTask) -> str:
    return f"{st.task.name} scheduled on {st.machine.name} from {st.start_time} to {st.end_time}"


def dump_schedule(
    solution: Schedule,
    instance: SchedulingInstance,
):
    jobs = instance.jobs

    # Create a mapping from task_id to ScheduledTask for easier lookup
    scheduled_tasks_map: dict[str, ScheduledTask] = {}
    for _, scheduled_tasks in solution.mapping.items():
        for st in scheduled_tasks:
            scheduled_tasks_map[st.task.id] = st

    cprint("[bold green]Generated Schedule:[/bold green]")
    for job in jobs:
        cprint(f"[bold blue]Job {job.name}:[/bold blue]")
        prev_st: ScheduledTask | None = None
        for task in job.tasks:
            # Get the scheduled task.
            st = scheduled_tasks_map.get(task.id)
            if not st:
                cprint(f"    [red]Task not found in schedule.[/red]")
                continue
            # Print the travel time.
            if prev_st:
                travel_time = instance.get_travel_time(prev_st.machine, st.machine)
                if travel_time > 0:
                    cprint(
                        f"    [yellow]Travel from "
                        f"{prev_st.machine.name} to "
                        f"{st.machine.name} taking "
                        f"{travel_time}[/yellow]"
                    )
            cprint(f"  [cyan]{scheduled_task_to_str(st)}[/cyan]")
            prev_st = st


def main():

    args = parse_args()
    instance = load_instance(args.instance)

    machines = instance.machines
    jobs = instance.jobs

    machine_dict = {m.id: m for m in machines}

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

    solution = solver.schedule()

    if not validate_schedule(solution, instance):
        cerror("Generated schedule is invalid.")

    dump_schedule(solution, instance)

    plot_gantt_chart(solution)


if __name__ == "__main__":
    main()
