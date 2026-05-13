from typing import override

from frost_planner.core.schedule import Schedule
from frost_planner.executor.base_executor import BaseExecutor
from frost_planner.solver.base_solver import BaseSolver


class StaticExecutor(BaseExecutor):
    """Static executor that follows a fixed schedule without re-solving.

    This executor computes the schedule once at the beginning and executes it
    without any adjustments, regardless of any changes in the environment or
    job arrivals.

    Attributes:
        solver (BaseSolver): The solver used to compute the initial schedule.
        live_plot (bool): Whether to enable live plotting of the schedule.
        schedule (Schedule): The fixed schedule computed at initialization.
    """

    def __init__(self, solver: BaseSolver, live_plot: bool = False):
        super().__init__(solver, live_plot=live_plot)
        self.schedule: Schedule = self.solver.schedule()

    @override
    def update_schedule(self, start_time: int = 0) -> Schedule:
        # Static executor doesn't re-solve, just returns the initial plan
        return self.schedule
