from typing_extensions import override

from frost_planner.core.schedule import Schedule
from frost_planner.executor.base_executor import BaseExecutor
from frost_planner.solver.base_solver import BaseSolver


class StaticExecutor(BaseExecutor):
    def __init__(self, solver: BaseSolver):
        super().__init__(solver)
        self.schedule: Schedule = self.solver.schedule()

    @override
    def update_schedule(self, start_time: int = 0) -> Schedule:
        return self.schedule
