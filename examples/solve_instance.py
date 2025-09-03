import time
import argparse
from frost_sheet.core.schedule import Schedule, ScheduledTask
from frost_sheet.core.validate import validate_schedule
from frost_sheet.core.base import SchedulingInstance
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.solver.stochastic_solver import StochasticSolver
from frost_sheet.solver.genetic_solver import GeneticAlgorithmSolver
from frost_sheet.visualization.gantt import plot_gantt_chart
from frost_sheet.utils import cprint, cerror, crule
from frost_sheet.core.metrics import (
    calculate_makespan,
    calculate_total_flow_time,
    calculate_lateness,
)
from frost_sheet.generator.instance_generator import load_instance_from_json


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
        choices=["dummy", "stochastic", "genetic"],
        help="Solver to use for scheduling",
    )
    return parser.parse_args()


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

    crule("Generated Schedule", style="blue")
    for job in jobs:
        job_start_time = solution.get_job_start_time(job)
        job_end_time = solution.get_job_end_time(job)
        cprint(
            f"  [blue]Job {job.name} (Due Date: {job.due_date}, "
            f"Start: {job_start_time}, End: {job_end_time}):[/blue]"
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
    crule("", style="blue")


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
    cprint("[blue]Schedule Metrics:[/blue]")
    cprint(f"  [blue]Makespan:[/blue] {makespan}")
    cprint(f"  [blue]Total Flow Time:[/blue] {total_flow_time}")
    cprint("  [blue]Lateness by Job:[/blue]")
    for job_name, lateness in lateness_by_job.items():
        cprint(f"    [blue]{job_name}:[/blue]", end=" ")
        if lateness > 0:
            cprint(f"[red]{lateness} (Late)[/red]")
        else:
            cprint(f"[green]{lateness} (On Time)[/green]")


def main() -> None:
    args = parse_args()

    cprint(f"Loading instance [green]{args.instance}[/green]...", style="yellow")

    instance = load_instance_from_json(args.instance)

    cprint("Loaded Scheduling Instance:")
    cprint(f"  Machines : {len(instance.machines)}")
    cprint(f"  Jobs     : {len(instance.jobs)}")
    cprint(f"  Tasks    : {len([task for job in instance.jobs for task in job.tasks])}")

    solver: BaseSolver
    if args.solver == "dummy":
        solver = DummySolver(instance=instance)
    elif args.solver == "genetic":
        solver = GeneticAlgorithmSolver(instance=instance)
    else:
        solver = StochasticSolver(instance=instance)

    cprint("Solving...", style="yellow")

    start_time = time.time()
    solution = solver.schedule()
    end_time = time.time()

    dump_schedule(solution, instance)

    cprint(f"Scheduling completed in {end_time - start_time:.4f} seconds.", style="green")

    cprint("Validating schedule...", style="yellow")

    if not validate_schedule(solution, instance):
        cerror("  Generated schedule is invalid.")
    else:
        cprint("  Generated schedule is valid.", style="green")

    dump_metrics(solution, instance)

    if args.gantt:
        cprint("Plotting Gantt chart and saving to file...", style="yellow")
        plot_gantt_chart(solution, output_path="data/gantt_chart.png")


if __name__ == "__main__":
    main()
