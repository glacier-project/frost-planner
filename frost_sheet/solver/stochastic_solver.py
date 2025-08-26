import sys
from typing_extensions import override
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.core.schedule import ScheduledTask
from frost_sheet.core.base import Task, Job, SchedulingInstance


class StochasticSolver(BaseSolver):
    """Stochastic solver that uses randomization to find better schedules.

    This solver explores the solution space by exploring random and local neighbor solutions.

    Attributes:
        T (int): Number of iterations to perform.
        R (int): Number of random neighbors to explore per iteration.
    """

    def __init__(
        self,
        instance: SchedulingInstance,
        horizon: int = sys.maxsize,
        T: int = 100,
        R: int = 8,
    ) -> None:
        super().__init__(instance, horizon)

    def _get_random_neighbor(self, jobs: list[Job]) -> None:
        """Generate a random neighbor solution by swapping two jobs."""
        pass

    def _get_local_neighbor(self, tasks: list[Task]) -> None:
        """Generate a local neighbor solution by swapping two tasks within the same job."""
        pass

    @override
    def _allocate_tasks(
        self, machine_intervals: dict[str, list[tuple[int, int]]]
    ) -> list[ScheduledTask]:
        scheduled_tasks: dict[str, ScheduledTask] = {}

        # Find a permutation
        # Schedule n times
        # global job permutations
        # local task permutations

        return list(scheduled_tasks.values())
