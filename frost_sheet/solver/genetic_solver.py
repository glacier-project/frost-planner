import sys
import random
from typing_extensions import override
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.core.schedule import ScheduledTask
from frost_sheet.core.base import Job, SchedulingInstance
from frost_sheet.solver import _schedule_by_order
from copy import deepcopy


class GeneticAlgorithmSolver(BaseSolver):
    """
    Genetic Algorithm solver for job shop scheduling problems.

    This solver uses a genetic algorithm to find an optimized schedule
    by evolving a population of job order permutations.
    """

    def __init__(
        self,
        instance: SchedulingInstance,
        horizon: int = sys.maxsize,
        population_size: int = 100,
        generations: int = 500,
        mutation_rate: float = 0.01,
        crossover_rate: float = 0.9,
        elitism_count: int = 5,
    ) -> None:
        super().__init__(instance, horizon)
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elitism_count = elitism_count

    def _initialize_population(self) -> list[list[Job]]:
        """
        Initializes a population of random job permutations.
        Each individual in the population is a list of Job objects,
        representing a job processing order.
        """
        population = []
        jobs = list(self.instance.jobs)
        for _ in range(self.population_size):
            random.shuffle(jobs)
            population.append(list(jobs))
        return population

    def _evaluate_fitness(
        self,
        job_permutation: list[Job],
        machine_intervals: dict[str, list[tuple[int, int]]],
    ) -> tuple[list[ScheduledTask], float]:
        """
        Evaluates the fitness of a job permutation.
        Fitness is based on the makespan (lower makespan = higher fitness).
        Returns the scheduled tasks and the makespan.
        """
        # Deepcopy machine_intervals to ensure each evaluation starts fresh
        temp_machine_intervals = deepcopy(machine_intervals)
        scheduled_tasks: list[ScheduledTask] = _schedule_by_order(
            self.instance,
            job_permutation,
            self.instance.machines,
            temp_machine_intervals,
            self.horizon,
            self.instance.travel_times,
            self.machine_id_map,
            self.suitable_machines_map,
        )
        makespan = (
            max(st.end_time for st in scheduled_tasks) if scheduled_tasks else 0.0
        )
        return scheduled_tasks, makespan

    def _select_parents(
        self, population: list[list[Job]], fitnesses: list[float]
    ) -> list[list[Job]]:
        """
        Selects parents for the next generation using tournament selection.
        """
        selected_parents = []
        # Assuming lower makespan is better, so we want to select individuals
        # with lower fitness values.
        # For tournament selection, pick a few individuals randomly and select
        # the best among them.
        tournament_size = 5  # Example tournament size
        for _ in range(self.population_size):
            tournament_contenders = random.sample(
                list(zip(population, fitnesses)), tournament_size
            )
            # Select the individual with the minimum makespan (best fitness)
            winner = min(tournament_contenders, key=lambda x: x[1])[0]
            selected_parents.append(winner)
        return selected_parents

    def _crossover(
        self, parent1: list[Job], parent2: list[Job]
    ) -> tuple[list[Job], list[Job]]:
        size = len(parent1)
        if size < 2:
            return list(parent1), list(parent2)

        point1, point2 = sorted(random.sample(range(size), 2))

        offspring1: list[Job | None] = [None] * size
        offspring2: list[Job | None] = [None] * size

        # Copy segment from parent1 to offspring1
        offspring1[point1:point2] = parent1[point1:point2]
        # Copy segment from parent2 to offspring2
        offspring2[point1:point2] = parent2[point1:point2]

        # Keep track of jobs already placed in the segment
        offspring1_segment_jobs: set[Job] = set(
            job for job in offspring1[point1:point2] if job is not None
        )
        offspring2_segment_jobs: set[Job] = set(
            job for job in offspring2[point1:point2] if job is not None
        )

        # Fill offspring1
        p2_idx = 0
        for i in range(size):
            if offspring1[i] is None:
                # Find next available job from parent2 that is not in the segment
                while parent2[p2_idx] in offspring1_segment_jobs:
                    p2_idx = (p2_idx + 1) % size
                offspring1[i] = parent2[p2_idx]
                # Add to the set of placed jobs
                offspring1_segment_jobs.add(parent2[p2_idx])
                p2_idx = (p2_idx + 1) % size

        # Fill offspring2
        p1_idx = 0
        for i in range(size):
            if offspring2[i] is None:
                # Find next available job from parent1 that is not in the segment
                while parent1[p1_idx] in offspring2_segment_jobs:
                    p1_idx = (p1_idx + 1) % size
                offspring2[i] = parent1[p1_idx]
                # Add to the set of placed jobs.
                offspring2_segment_jobs.add(parent1[p1_idx])
                p1_idx = (p1_idx + 1) % size

        # Make sure offspring are valid permutations
        assert all(job is not None for job in offspring1)
        assert all(job is not None for job in offspring2)

        return offspring1, offspring2

    def _mutate(self, job_permutation: list[Job]) -> list[Job]:
        """
        Performs a simple swap mutation on a job permutation.
        """
        if len(job_permutation) < 2:
            return job_permutation
        idx1, idx2 = random.sample(range(len(job_permutation)), 2)
        job_permutation[idx1], job_permutation[idx2] = (
            job_permutation[idx2],
            job_permutation[idx1],
        )
        return job_permutation

    @override
    def _allocate_tasks(
        self, machine_intervals: dict[str, list[tuple[int, int]]]
    ) -> list[ScheduledTask]:
        best_solution_tasks: list[ScheduledTask] = []
        best_makespan: float = float("inf")

        population: list[list[Job]] = self._initialize_population()

        for generation in range(self.generations):
            # Evaluate fitness for the current population
            evaluated_population: list[tuple[list[Job], list[ScheduledTask], float]] = (
                []
            )
            for individual in population:
                scheduled_tasks: list[ScheduledTask]
                makespan: float
                scheduled_tasks, makespan = self._evaluate_fitness(
                    individual, machine_intervals
                )
                evaluated_population.append((individual, scheduled_tasks, makespan))

            # Sort by makespan (ascending, as lower is better)
            evaluated_population.sort(key=lambda x: x[2])

            # Update best solution found so far
            current_best_tasks: list[ScheduledTask]
            current_best_makespan: float
            _, current_best_tasks, current_best_makespan = evaluated_population[0]
            if current_best_makespan < best_makespan:
                best_makespan = current_best_makespan
                best_solution_tasks = current_best_tasks

            # Create next generation
            new_population: list[list[Job]] = []

            # Elitism: Carry over the best individuals
            for i in range(self.elitism_count):
                new_population.append(evaluated_population[i][0])

            # Fill the rest of the population
            while len(new_population) < self.population_size:
                # Select from current best.
                parent1: list[Job]
                parent2: list[Job]
                parent1, parent2 = random.sample(
                    [ind[0] for ind in evaluated_population], 2
                )

                # Crossover
                if random.random() < self.crossover_rate:
                    offspring1, offspring2 = self._crossover(parent1, parent2)
                else:
                    offspring1, offspring2 = list(parent1), list(parent2)

                # Mutation
                if random.random() < self.mutation_rate:
                    offspring1 = self._mutate(offspring1)
                if random.random() < self.mutation_rate:
                    offspring2 = self._mutate(offspring2)

                new_population.append(offspring1)
                if len(new_population) < self.population_size:
                    new_population.append(offspring2)

            population = new_population

        return best_solution_tasks
