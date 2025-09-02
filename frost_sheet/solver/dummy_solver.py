import sys
from typing_extensions import override
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.core.schedule import ScheduledTask
from frost_sheet.core.base import SchedulingInstance
from frost_sheet.solver import _schedule_by_order


class DummySolver(BaseSolver):
    """Dummy solver that does not perform any optimization.

    This solver simply allocates tasks to the machines based on their order in the instance.
    """

    def __init__(
        self, instance: SchedulingInstance, horizon: int = sys.maxsize
    ) -> None:
        super().__init__(instance, horizon)

    @override
    def _allocate_tasks(
        self, machine_intervals: dict[str, list[tuple[int, int]]]
    ) -> list[ScheduledTask]:
        return _schedule_by_order(
            self.instance.jobs,
            self.instance.machines,
            machine_intervals,
            self.horizon,
            self.instance.travel_times,
        )
