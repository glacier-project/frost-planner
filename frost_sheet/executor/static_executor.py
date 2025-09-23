from frost_sheet.core.base import SchedulingInstance
from frost_sheet.core.schedule import Schedule
from frost_sheet.executor.base_executor import BaseExecutor
from frost_sheet.solver.base_solver import BaseSolver
from typing_extensions import override

class StaticExecutor(BaseExecutor):

    def __init__(self, solver: BaseSolver):
        super().__init__(solver)
        self.schedule = self.solver.schedule()

    @override
    def update_schedule(self) -> Schedule:
        return self.schedule
    

    
