# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import random
import sys
from copy import deepcopy
from typing import override

from frost_planner.core.base import Job, SchedulingInstance, _sort_tasks
from frost_planner.core.objective import (
    ObjectiveWeights,
    calculate_objective_value,
)
from frost_planner.core.schedule import ScheduledTask
from frost_planner.solver import _create_schedule, _schedule_by_order
from frost_planner.solver.base_solver import BaseSolver


class StochasticSolver(BaseSolver):
    """Stochastic solver that uses randomization to find better schedules.

    This solver explores the solution space by exploring random and local
    neighbor solutions.

    Attributes:
        instance (SchedulingInstance):
            The scheduling instance to solve.
        horizon (int):
            The time horizon for scheduling.
        T (int):
            Maximum number of iterations.
        B (int):
            Budget for exploration, in terms of number of iterations.
        R (int):
            Number of random neighbors to explore per iteration.
        alpha (float):
            Exploration rate.
        t_idle (int):
            Maximum number of consecutive idle iterations.

    """

    def __init__(
        self,
        instance: SchedulingInstance,
        horizon: int = sys.maxsize,
        T: int = 1000,  # noqa: N803 — math convention (temperature)
        B: int = 400,  # noqa: N803 — math convention (budget)
        R: int = 16,  # noqa: N803 — math convention (remote neighbors)
        alpha: float = 0.4,
        t_idle: int = 10,
        machine_intervals: dict[str, list[tuple[int, int]]] | None = None,
        objective: ObjectiveWeights | None = None,
    ) -> None:
        super().__init__(instance, horizon, machine_intervals, objective)
        self.T = T
        self.B = B
        self.R = R
        self.alpha = alpha
        self.t_idle = t_idle

    def _get_random_neighbor(self, jobs: list[Job]) -> list[Job]:
        """Generate a random neighbor solution by swapping two jobs.

        Args:
            jobs (list[Job]):
                List of jobs to generate a neighbor for.

        Returns:
            list[Job]:
                A list of jobs with two jobs swapped.

        """
        if len(jobs) < 2:
            return jobs

        idx1, idx2 = random.sample(range(len(jobs)), 2)
        jobs[idx1], jobs[idx2] = jobs[idx2], jobs[idx1]
        return jobs

    def _get_local_neighbor(self, jobs: list[Job]) -> list[Job]:
        """Generate a local neighbor by swapping two tasks within the same job.

        Args:
            jobs (list[Job]):
                List of jobs to generate a neighbor for.

        Returns:
            list[Job]:
                A list of jobs with two tasks swapped.
        """
        if not jobs:
            return jobs

        # Select a job to modify
        job_to_modify = random.choice(jobs)
        job_index = jobs.index(job_to_modify)

        if len(job_to_modify.tasks) < 2:
            return jobs

        # Create a mutable copy of the tasks list
        tasks_copy = list(job_to_modify.tasks)

        # Swap two tasks in the copy
        idx1, idx2 = random.sample(range(len(tasks_copy)), 2)
        tasks_copy[idx1], tasks_copy[idx2] = tasks_copy[idx2], tasks_copy[idx1]

        # Sort tasks and create a new Job instance
        new_tasks = _sort_tasks(tasks_copy)
        new_job = Job(
            id=job_to_modify.id,
            name=job_to_modify.name,
            tasks=new_tasks,
            priority=job_to_modify.priority,
            due_date=job_to_modify.due_date,
        )

        # Replace the old job with the new job in the jobs list
        jobs[job_index] = new_job

        return jobs

    def _sort_jobs_random(self, jobs: list[Job]) -> list[Job]:
        """Sort jobs randomly.

        Args:
            jobs (list[Job]):
                List of jobs to sort.

        Returns:
            list[Job]:
                Randomly sorted list of jobs.

        """
        random.shuffle(jobs)
        return jobs

    def _evaluate_solution(
        self,
        jobs: list[Job],
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> tuple[list[ScheduledTask], float]:
        """Evaluate the quality of a solution using configured objectives.

        Args:
            jobs (list[Job]):
                List of jobs to evaluate.
            machine_intervals (dict[str, list[tuple[int, int]]]):
                The availability intervals for each machine.
            start_time (int):
                The global lower bound for task start times.

        Returns:
            tuple[list[ScheduledTask], float]:
                A tuple containing the scheduled tasks and objective value.

        """
        machine_intervals = deepcopy(machine_intervals)
        locked_tasks_map = {st.task.id: st for st in self.locked_tasks.values()}
        scheduled_tasks = _schedule_by_order(
            self.instance,
            jobs,
            self.instance.machines,
            machine_intervals,
            self.horizon,
            self.instance.travel_times,
            self.machine_id_map,
            self.suitable_machines_map,
            initial_scheduled_tasks=locked_tasks_map,
            min_time=start_time,
        )

        schedule = _create_schedule(
            scheduled_tasks=scheduled_tasks,
            machines=self.instance.machines,
        )
        return scheduled_tasks, calculate_objective_value(
            schedule,
            self.instance,
            self.objective,
        )

    @override
    def _allocate_tasks(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> list[ScheduledTask]:
        # init random
        alpha = self.alpha
        B = self.B  # noqa: N806 — math convention (budget)
        R = self.R  # noqa: N806 — math convention (remote neighbors)
        local_iterations = round(((1 - alpha) * B) / R)
        jobs = self._sort_jobs_random(list(self.instance.jobs))
        solution, best_score = self._evaluate_solution(
            jobs, machine_intervals, start_time=start_time
        )
        idle_iterations = 0

        for _ in range(self.T):
            if idle_iterations > self.t_idle:
                break

            local_jobs = jobs
            local_solution = solution
            current_score = float("inf")

            # alpha*B local explorations
            for _ in range(int(self.alpha * B)):
                local_neighbor = self._get_local_neighbor(local_jobs.copy())
                local_solution, local_score = self._evaluate_solution(
                    local_neighbor, machine_intervals, start_time=start_time
                )
                if local_score < current_score:
                    local_jobs = local_neighbor
                    current_score = local_score

            for _ in range(R):
                remote_neighbor = self._get_random_neighbor(local_jobs.copy())

                for _ in range(local_iterations):
                    local_neighbor = self._get_local_neighbor(
                        remote_neighbor.copy()
                    )
                    local_solution, local_score = self._evaluate_solution(
                        local_neighbor, machine_intervals, start_time=start_time
                    )
                    if local_score < current_score:
                        local_jobs = local_neighbor
                        current_score = local_score

            if current_score < best_score:
                jobs = local_jobs
                solution = local_solution
                best_score = current_score
                idle_iterations = 0
            else:
                # number of idle iterations
                idle_iterations += 1

        return solution
