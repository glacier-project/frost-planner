from typing_extensions import override

from frost_planner.core.schedule import Schedule
from frost_planner.executor.base_executor import BaseExecutor
from frost_planner.solver.base_solver import BaseSolver


class DynamicExecutor(BaseExecutor):
    def __init__(self, solver: BaseSolver, live_plot: bool = False):
        super().__init__(solver, live_plot=live_plot)

    @override
    def update_schedule(self, start_time: int = 0) -> Schedule:
        self.schedule: Schedule = self.solver.schedule(start_time=start_time)
        self._plot_needs_update = True
        return self.schedule
