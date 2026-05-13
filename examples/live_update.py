# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import time

from frost_planner.core.base import TaskStatus
from frost_planner.executor.dynamic_executor import DynamicExecutor
from frost_planner.generator.instance_generator import load_instance_from_json
from frost_planner.solver.stochastic_solver import StochasticSolver
from frost_planner.utils import cprint, crule


def main() -> None:
    """Event-driven scheduling simulation."""
    crule("Event-driven Scheduling Simulation", style="blue")

    instance_path = "data/instance_3.json"
    cprint(
        f"Loading instance from [green]{instance_path}[/green]...",
        style="yellow",
    )
    full_instance = load_instance_from_json(instance_path)

    all_jobs = list(full_instance.jobs)
    initial_jobs = all_jobs[:5]
    pending_jobs = all_jobs[5:]

    current_instance = full_instance.model_copy(
        update={"jobs": list(initial_jobs)}
    )
    solver = StochasticSolver(instance=current_instance, t=100, b=200)
    executor = DynamicExecutor(solver, live_plot=True)

    cprint(
        "Simulation starting. Jumping directly to the next events!",
        style="green",
    )

    try:
        # Simulation loop using event jumps
        step = 0
        while True:
            step += 1

            # New Job arrival (re-scheduling)
            if step > 0 and step % 10 == 0 and pending_jobs:
                new_job = pending_jobs.pop(0)
                initial_jobs.append(new_job)
                cprint(
                    f"\n[bold magenta]>>> Time {executor.current_time}: New Job"
                    f" Arrived: {new_job.name}[/bold magenta]"
                )
                current_instance = current_instance.model_copy(
                    update={"jobs": list(initial_jobs)}
                )
                solver.update_instance(current_instance)
                executor.update_schedule(start_time=executor.current_time)

            # Compute next jump
            next_event_time = executor.get_next_event_time()
            if next_event_time is None:
                # No future events planned
                break

            # Advance to the next event
            delta = next_event_time - executor.current_time
            executor.step(delta_time=delta)
            now = executor.current_time

            cprint(f"\n[bold yellow]>>> Time Jump to: {now}[/bold yellow]")

            # Since we jumped exactly to the next event, we process whatever
            # changed
            current_schedule = executor.get_current_schedule()
            for st in current_schedule.get_tasks():
                if (
                    st.end_time <= now
                    and st.task.status != TaskStatus.COMPLETED
                ):
                    executor.task_completed(st)
                    cprint(f"  [green]✔ Task {st.task.name} finished.[/green]")
                elif (
                    st.start_time <= now < st.end_time
                    and st.task.status != TaskStatus.IN_PROGRESS
                ):
                    executor.task_started(st)
                    cprint(f"  [red]▶ Task {st.task.name} started.[/red]")

            # Re-scheduling
            executor.update_schedule(start_time=now)

            # Print status
            locked_count = len(solver.locked_tasks)
            total_tasks = sum(len(j.tasks) for j in initial_jobs)
            cprint(f"  Status: {locked_count}/{total_tasks} tasks locked.")

            # Redraw explicitly after all state changes for this tick are done
            # (Throttled internally by the executor)
            executor.update_plot()

            time.sleep(0.3)

            # Exit if everything is done
            all_tasks_locked = locked_count == total_tasks
            all_tasks_completed = all(
                st.task.status == TaskStatus.COMPLETED
                for st in solver.locked_tasks.values()
            )
            if not pending_jobs and all_tasks_locked and all_tasks_completed:
                cprint(
                    "\n[bold green]Success: All tasks completed![/bold green]"
                )
                time.sleep(2)
                break

    except KeyboardInterrupt:
        cprint("\nInterrupted by user.", style="red")
    finally:
        executor.close()


if __name__ == "__main__":
    main()
