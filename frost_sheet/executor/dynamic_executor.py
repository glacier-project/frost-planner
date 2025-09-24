from typing_extensions import override

from frost_sheet.core.schedule import Schedule
from frost_sheet.executor.base_executor import BaseExecutor
from frost_sheet.solver.base_solver import BaseSolver


class DynamicExecutor(BaseExecutor):
    def __init__(self, solver: BaseSolver):
        super().__init__(solver)

    @override
    def update_schedule(self, start_time: int = 0) -> Schedule:
        self.schedule: Schedule = self.solver.schedule(start_time=start_time)
        return self.schedule
