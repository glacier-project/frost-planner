import argparse
from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.core.validate import validate_schedule
from frost_sheet.core.base import SchedulingInstance
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.solver.stochastic_solver import StochasticSolver
from frost_sheet.visualization.gantt import plot_gantt_chart
from frost_sheet.utils import cprint, cerror


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate random job-shop scheduling instances"
    )
    parser.add_argument(
        "-g",
        "--gantt",
        action="store_true",
        help="Whether to plot a Gantt chart of the schedule",
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
    """
    Load a scheduling instance from a JSON file.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        SchedulingInstance: The loaded scheduling instance.
    """
    with open(file_path, "r") as f:
        return SchedulingInstance.model_validate_json(f.read())


def scheduled_task_to_str(st: ScheduledTask) -> str:
    """
    Convert a ScheduledTask to a string representation.

    Args:
        st (ScheduledTask): The scheduled task to convert.

    Returns:
        str: The string representation of the scheduled task.
    """
    return (
        f"{st.task.name} scheduled on {st.machine.name}"
        f" from {st.start_time} to {st.end_time}"
    )


def dump_schedule(
    solution: Schedule,
    instance: SchedulingInstance,
) -> None:
    jobs = instance.jobs

    cprint("[bold green]Generated Schedule:[/bold green]")
    for job in jobs:
        cprint(f"  [bold blue]Job {job.name}:[/bold blue]")
        prev_st: ScheduledTask | None = None
        for task in job.tasks:
            # Get the scheduled task.
            st = solution.get_task_mapping(task)
            if not st:
                cprint("  [red]Task not found in schedule.[/red]")
                continue
            # Print the travel time.
            if prev_st:
                travel_time = instance.get_travel_time(prev_st.machine, st.machine)
                if travel_time > 0:
                    cprint(
                        f"      [yellow]Travel from "
                        f"{prev_st.machine.name} to "
                        f"{st.machine.name} taking "
                        f"{travel_time}[/yellow]"
                    )
            cprint(f"    [cyan]{scheduled_task_to_str(st)}[/cyan]")
            prev_st = st


def main() -> None:
    args = parse_args()

    cprint("Loading instance...", style="bold cyan")

    instance = load_instance(args.instance)

    cprint("Loaded Scheduling Instance:")
    cprint(f"  Machines : {len(instance.machines)}")
    cprint(f"  Jobs     : {len(instance.jobs)}")
    cprint(f"  Tasks    : {len([task for job in instance.jobs for task in job.tasks])}")

    solver: BaseSolver
    if args.solver == "dummy":
        solver = DummySolver(instance=instance)
    else:
        solver = StochasticSolver(instance=instance)

    cprint("Solving...", style="bold cyan")

    solution = solver.schedule()

    dump_schedule(solution, instance)

    cprint("Validating schedule...", style="bold cyan")

    if not validate_schedule(solution, instance):
        cerror("  Generated schedule is invalid.")
    else:
        cprint("  Generated schedule is valid.", style="bold green")

    if args.gantt:
        plot_gantt_chart(solution)


if __name__ == "__main__":
    main()
