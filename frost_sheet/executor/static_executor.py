from core.base import SchedulingInstance
from core.schedule import Schedule
from frost_sheet.executor.base_executor import BaseExecutor
from solver.base_solver import BaseSolver
from typing_extensions import override

class StaticExecutor(BaseExecutor):

    def __init__(self, solver: BaseSolver, instance: SchedulingInstance):
        super().__init__(solver, instance)
        self.schedule = self.solver.schedule()

    @override
    def update_schedule(self) -> Schedule:
        return self.schedule
    

    
