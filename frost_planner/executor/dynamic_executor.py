from typing import override

from frost_planner.core.schedule import Schedule
from frost_planner.executor.base_executor import BaseExecutor
from frost_planner.solver.base_solver import BaseSolver


class DynamicExecutor(BaseExecutor):
    """Dynamic executor that re-solves the scheduling problem at each update.

    This executor re-computes the schedule whenever an update is triggered,
    allowing it to adapt to changes in the environment, such as new job arrivals
    or task completions. It uses the provided solver to compute the new schedule
    based on the current state of the system.

    Attributes:
        solver (BaseSolver): The solver used to compute the schedule.
        live_plot (bool): Whether to enable live plotting of the schedule.
    """

    def __init__(self, solver: BaseSolver, live_plot: bool = False):
        super().__init__(solver, live_plot=live_plot)

    @override
    def update_schedule(self, start_time: int = 0) -> Schedule:
        self.schedule: Schedule = self.solver.schedule(start_time=start_time)
        self._plot_needs_update = True
        return self.schedule
