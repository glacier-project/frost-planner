# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

from abc import ABC, abstractmethod

from frost_planner.core.base import TaskStatus
from frost_planner.core.schedule import Schedule, ScheduledTask
from frost_planner.solver.base_solver import BaseSolver
from frost_planner.visualization.gantt import LiveGanttChart


class BaseExecutor(ABC):
    """Base executor class for managing task execution and schedule updates.

    Attributes:
        solver (BaseSolver): The solver used to generate the schedule.
        live_plot (bool): Whether to show a live Gantt chart during execution.
    """

    def __init__(self, solver: BaseSolver, live_plot: bool = False):
        self.solver = solver
        self.schedule: Schedule | None = None
        self.current_time = 0
        self.live_plot = live_plot
        self.chart = LiveGanttChart() if live_plot else None
        self._plot_needs_update = True
        self.update_task_status()

    @abstractmethod
    def update_schedule(self, start_time: int = 0) -> Schedule:
        """Update and return the current schedule."""

    def get_current_schedule(self) -> Schedule:
        """Get the current schedule."""
        if self.schedule is None:
            self.schedule = self.update_schedule(start_time=self.current_time)

        return self.schedule

    def get_next_event_time(self) -> int | None:
        """Returns the time of the next event after the current time.

        This method looks at the current schedule and finds the next start or
        end time of any task that is greater than the current time. This allows
        the executor to know when the next task will start or finish, which can
        be used to advance the simulation time accordingly.
        """
        schedule = self.get_current_schedule()
        event_time: int | None = None
        for st in schedule.get_tasks():
            if st.start_time > self.current_time and (
                event_time is None or st.start_time < event_time
            ):
                event_time = st.start_time
            if st.end_time > self.current_time and (
                event_time is None or st.end_time < event_time
            ):
                event_time = st.end_time
        return event_time

    def step(self, delta_time: int) -> None:
        """Advance the simulation time.

        Args:
            delta_time (int): The amount of time to advance.
        """
        if delta_time > 0:
            self.current_time += delta_time
            self._plot_needs_update = True

    def update_plot(self, force: bool = False) -> None:
        """Update the live Gantt chart if enabled and state has changed."""
        if self.chart and (self._plot_needs_update or force):
            self.chart.update(
                self.get_current_schedule(), current_time=self.current_time
            )
            self._plot_needs_update = False

    def close(self) -> None:
        """Close resources (like the live chart)."""
        if self.chart:
            self.chart.close()

    def task_started(self, tasks: list[ScheduledTask] | ScheduledTask) -> None:
        """Mark tasks as started (IN_PROGRESS) and lock them in the solver."""
        if isinstance(tasks, ScheduledTask):
            tasks = [tasks]

        for st in tasks:
            st.task.status = TaskStatus.IN_PROGRESS

        self.solver.lock_tasks(tasks)
        self._plot_needs_update = True

    def task_completed(
        self, tasks: list[ScheduledTask] | ScheduledTask
    ) -> None:
        """Mark tasks as completed and lock them in the solver."""
        if isinstance(tasks, ScheduledTask):
            tasks = [tasks]

        for st in tasks:
            st.task.status = TaskStatus.COMPLETED

        self.solver.lock_tasks(tasks)
        # Completing tasks might make others READY
        self.update_task_status()
        self._plot_needs_update = True

    def task_failed(self, scheduled_task: ScheduledTask) -> None:
        """Mark a task as failed."""
        scheduled_task.task.status = TaskStatus.FAILED
        self._plot_needs_update = True

    def update_task_status(self) -> None:
        """Update the status of all tasks based on dependencies.

        A task becomes READY if all its dependencies are COMPLETED, and it is
        not already IN_PROGRESS or COMPLETED.
        """
        instance = self.solver.instance
        for job in instance.jobs:
            for task in job.tasks:
                if task.status != TaskStatus.WAITING:
                    continue

                if len(task.dependencies) == 0:
                    task.status = TaskStatus.READY
                    continue

                all_deps_done = True
                for dependency in task.dependencies:
                    predecessor_task = job.find_task(dependency)
                    if (
                        predecessor_task is None
                        or predecessor_task.status != TaskStatus.COMPLETED
                    ):
                        all_deps_done = False
                        break

                if all_deps_done:
                    task.status = TaskStatus.READY

    def next_ready_tasks(self) -> list[tuple[ScheduledTask, str]]:
        """Return the next tasks ready to be executed on each machine."""
        schedule = self.get_current_schedule()
        instance = self.solver.instance

        ready_tasks: list[tuple[ScheduledTask, str]] = []
        for machine in instance.machines:
            scheduled_tasks = schedule.get_machine_tasks(machine)

            for task in scheduled_tasks:
                if task.task.status == TaskStatus.COMPLETED:
                    continue
                if task.task.status == TaskStatus.IN_PROGRESS:
                    break
                if task.task.status == TaskStatus.READY:
                    ready_tasks.append((task, machine.id))
                    break

        return ready_tasks
