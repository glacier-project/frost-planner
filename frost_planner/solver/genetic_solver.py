# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import random
import sys
from typing import override

from frost_planner.core.base import Job, SchedulingInstance
from frost_planner.core.objective import ObjectiveWeights
from frost_planner.core.schedule import ScheduledTask
from frost_planner.solver.base_solver import BaseSolver


class GeneticAlgorithmSolver(BaseSolver):
    """Genetic Algorithm solver for job shop scheduling problems.

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
        machine_intervals: dict[str, list[tuple[int, int]]] | None = None,
        objective: ObjectiveWeights | None = None,
    ) -> None:
        super().__init__(instance, horizon, machine_intervals, objective)
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elitism_count = elitism_count

    def _initialize_population(self) -> list[list[Job]]:
        """Initialize a population seeded by structured orderings.

        The first slots come from the analysis's structured
        candidate orderings (instance order, SPT, LPT, EDD, min slack,
        a few seeded shuffles); the remaining slots are random
        permutations. Seeding with non-random orderings gives the GA
        a head start and stops the first generations being pure noise.
        """
        population: list[list[Job]] = [
            list(ordering)
            for ordering in self.analysis.candidate_job_orderings()
        ]
        if len(population) > self.population_size:
            population = population[: self.population_size]
        jobs = list(self.instance.jobs)
        while len(population) < self.population_size:
            random.shuffle(jobs)
            population.append(list(jobs))
        return population

    def _evaluate_fitness(
        self,
        job_permutation: list[Job],
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> tuple[list[ScheduledTask], float]:
        """Evaluates the fitness of a job permutation.

        Fitness is based on the configured objective value.
        Returns the scheduled tasks and the objective value.
        """
        result = self._greedy_evaluate(
            job_permutation,
            machine_intervals,
            start_time=start_time,
        )
        return result.scheduled_tasks, result.objective

    def _select_parents(
        self, population: list[list[Job]], fitnesses: list[float]
    ) -> list[list[Job]]:
        """Selects parents for the next gen using tournament selection."""
        selected_parents = []
        # Lower objective values are better, so select individuals
        # with lower fitness values.
        # For tournament selection, pick a few individuals randomly and select
        # the best among them.
        tournament_size = 5  # Example tournament size
        for _ in range(self.population_size):
            tournament_contenders = random.sample(
                list(zip(population, fitnesses, strict=False)), tournament_size
            )
            # Select the individual with the minimum objective (best fitness)
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
        offspring1_segment_jobs: set[Job] = {
            job for job in offspring1[point1:point2] if job is not None
        }
        offspring2_segment_jobs: set[Job] = {
            job for job in offspring2[point1:point2] if job is not None
        }

        # Fill offspring1
        p2_idx = 0
        for i in range(size):
            if offspring1[i] is None:
                # Find next available job from parent2 that is not in the
                # segment
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
                # Find next available job from parent1 that is not in the
                # segment
                while parent1[p1_idx] in offspring2_segment_jobs:
                    p1_idx = (p1_idx + 1) % size
                offspring2[i] = parent1[p1_idx]
                # Add to the set of placed jobs.
                offspring2_segment_jobs.add(parent1[p1_idx])
                p1_idx = (p1_idx + 1) % size

        return offspring1, offspring2  # type: ignore[return-value]

    def _mutate(self, job_permutation: list[Job]) -> list[Job]:
        """Performs a simple swap mutation on a job permutation."""
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
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> list[ScheduledTask]:
        best_solution_tasks: list[ScheduledTask] = []
        best_score: float = float("inf")

        population: list[list[Job]] = self._initialize_population()

        for _generation in range(self.generations):
            # Evaluate fitness for the current population
            evaluated_population: list[
                tuple[list[Job], list[ScheduledTask], float]
            ] = []
            for individual in population:
                scheduled_tasks: list[ScheduledTask]
                score: float
                scheduled_tasks, score = self._evaluate_fitness(
                    individual, machine_intervals, start_time=start_time
                )
                evaluated_population.append(
                    (individual, scheduled_tasks, score)
                )

            # Sort by objective value (ascending, as lower is better)
            evaluated_population.sort(key=lambda x: x[2])

            # Update best solution found so far
            current_bt: list[ScheduledTask]
            current_score: float
            _, current_bt, current_score = evaluated_population[0]
            if current_score < best_score:
                best_score = current_score
                best_solution_tasks = current_bt

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
