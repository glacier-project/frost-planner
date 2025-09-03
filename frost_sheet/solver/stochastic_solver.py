import sys
import random
from typing_extensions import override
from frost_sheet.solver import _schedule_by_order
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.core.schedule import ScheduledTask
from frost_sheet.core.base import Job, SchedulingInstance, _sort_tasks
from copy import deepcopy


class StochasticSolver(BaseSolver):
    """
    Stochastic solver that uses randomization to find better schedules.

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
        T: int = 1000,
        B: int = 400,
        R: int = 16,
        alpha: float = 0.4,
        t_idle: int = 10,
    ) -> None:
        super().__init__(instance, horizon)
        self.T = T
        self.B = B
        self.R = R
        self.alpha = alpha
        self.t_idle = t_idle

    def _get_random_neighbor(self, jobs: list[Job]) -> list[Job]:
        """
        Generate a random neighbor solution by swapping two jobs.

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
        """
        Generate a local neighbor solution by swapping two tasks within the same
        job.

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
        """
        Sort jobs randomly.

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
        self, jobs: list[Job], machine_intervals: dict[str, list[tuple[int, int]]]
    ) -> tuple[list[ScheduledTask], int]:
        """
        Evaluate the quality of a solution based on the makespan.

        Args:
            jobs (list[Job]):
                List of jobs to evaluate.
        Returns:
            tuple[list[ScheduledTask], int]:
                A tuple containing the scheduled tasks and the makespan.
        """
        machine_intervals = deepcopy(machine_intervals)
        scheduled_tasks = _schedule_by_order(
            self.instance,
            jobs,
            self.instance.machines,
            machine_intervals,
            self.horizon,
            self.instance.travel_times,
        )

        return scheduled_tasks, (
            max(task.end_time for task in scheduled_tasks) if scheduled_tasks else 0
        )

    @override
    def _allocate_tasks(
        self, machine_intervals: dict[str, list[tuple[int, int]]]
    ) -> list[ScheduledTask]:
        # init random
        alpha = self.alpha
        B = self.B
        R = self.R
        local_iterations = round(((1 - alpha) * B) / R)
        jobs = self._sort_jobs_random(list(self.instance.jobs))
        solution, makespan = self._evaluate_solution(jobs, machine_intervals)
        idle_iterations = 0

        for _ in range(self.T):
            if idle_iterations > self.t_idle:
                break

            local_jobs = jobs
            local_solution = solution
            current_makespan = sys.maxsize

            # αB local explorations
            for _ in range(int(self.alpha * self.B)):
                local_neighbor = self._get_local_neighbor(deepcopy(local_jobs))
                local_solution, local_makespan = self._evaluate_solution(
                    local_neighbor, machine_intervals
                )
                if local_makespan < makespan:
                    local_jobs = local_neighbor
                    local_solution = local_solution
                    current_makespan = local_makespan

            for _ in range(self.R):
                remote_neighbor = self._get_random_neighbor(deepcopy(local_jobs))

                for _ in range(local_iterations):
                    local_neighbor = self._get_local_neighbor(deepcopy(remote_neighbor))
                    local_solution, local_makespan = self._evaluate_solution(
                        local_jobs, machine_intervals
                    )
                    if local_makespan < makespan:
                        local_jobs = local_neighbor
                        local_solution = local_solution
                        current_makespan = local_makespan

            if current_makespan < makespan:
                jobs = local_jobs
                solution = local_solution
                makespan = current_makespan
                idle_iterations = 0
            else:
                # number of idle iterations
                idle_iterations += 1

        return solution
