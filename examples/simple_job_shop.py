import argparse
from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.core.validate import validate_schedule
from frost_sheet.core.base import SchedulingInstance
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.solver.stochastic_solver import StochasticSolver
from frost_sheet.visualization.gantt import plot_gantt_chart
from frost_sheet.utils import cprint, cerror
from frost_sheet.core.metrics import (
    calculate_makespan,
    calculate_total_flow_time,
    calculate_lateness,
)


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
    """
    Dumps the schedule information for the given solution and instance.

    Args:
        solution (Schedule):
            The generated schedule.
        instance (SchedulingInstance):
            The original scheduling instance.
    """

    jobs = instance.jobs

    cprint("[bold green]Generated Schedule:[/bold green]")
    for job in jobs:
        job_start_time = solution.get_job_start_time(job)
        job_end_time = solution.get_job_end_time(job)
        cprint(
            f"  [bold blue]Job {job.name} (Due Date: {job.due_date}, "
            f"Start: {job_start_time}, End: {job_end_time}):[/bold blue]"
        )
        prev_st: ScheduledTask | None = None
        scheduled_tasks: list[ScheduledTask] = []
        for task in job.tasks:
            st = solution.get_task_mapping(task)
            if st:
                scheduled_tasks.append(st)
            else:
                cprint("  [red]Task not found in schedule.[/red]")

        # Sort scheduled tasks by start time
        scheduled_tasks.sort(key=lambda x: x.start_time)

        for st in scheduled_tasks:
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


def dump_metrics(
    solution: Schedule,
    instance: SchedulingInstance,
) -> None:
    """
    Dumps the scheduling metrics for the given solution and instance.

    Args:
        solution (Schedule):
            The generated schedule.
        instance (SchedulingInstance):
            The original scheduling instance.
    """
    # Compute the schedule metrics.
    makespan = calculate_makespan(solution)
    total_flow_time = calculate_total_flow_time(solution)
    lateness_by_job = calculate_lateness(solution, instance)
    # Display the schedule metrics.
    cprint("\n[bold blue]Schedule Metrics:[/bold blue]")
    cprint(f"  [bold blue]Makespan:[/bold blue] {makespan}")
    cprint(f"  [bold blue]Total Flow Time:[/bold blue] {total_flow_time}")
    cprint("  [bold blue]Lateness by Job:[/bold blue]")
    for job_name, lateness in lateness_by_job.items():
        cprint(f"    [bold blue]{job_name}:[/bold blue]", end=" ")
        if lateness > 0:
            cprint(f"[red]{lateness} (Late)[/red]")
        else:
            cprint(f"[green]{lateness} (On Time)[/green]")


def main() -> None:
    args = parse_args()

    cprint("Loading instance...", style="yellow")

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

    cprint("Solving...", style="yellow")

    solution = solver.schedule()

    dump_schedule(solution, instance)

    cprint("Validating schedule...", style="yellow")

    if not validate_schedule(solution, instance):
        cerror("  Generated schedule is invalid.")
    else:
        cprint("  Generated schedule is valid.", style="bold green")

    dump_metrics(solution, instance)

    if args.gantt:
        cprint("Plotting Gantt chart and saving to file...", style="yellow")
        plot_gantt_chart(solution, output_path="data/gantt_chart.png")


if __name__ == "__main__":
    main()
