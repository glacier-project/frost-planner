# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import sys
from typing import override

from frost_planner.core.base import SchedulingInstance
from frost_planner.core.schedule import ScheduledTask
from frost_planner.solver import _schedule_by_order
from frost_planner.solver.base_solver import BaseSolver


class DummySolver(BaseSolver):
    """Dummy solver that does not perform any optimization.

    This solver simply allocates tasks to the machines based on their order in
    the instance.
    """

    def __init__(
        self,
        instance: SchedulingInstance,
        horizon: int = sys.maxsize,
        machine_intervals: dict[str, list[tuple[int, int]]] | None = None,
    ) -> None:
        super().__init__(instance, horizon, machine_intervals)

    @override
    def _allocate_tasks(
        self,
        machine_intervals: dict[str, list[tuple[int, int]]],
        start_time: int = 0,
    ) -> list[ScheduledTask]:
        locked_tasks_map = {st.task.id: st for st in self.locked_tasks.values()}
        return _schedule_by_order(
            self.instance,
            self.instance.jobs,
            self.instance.machines,
            machine_intervals,
            self.horizon,
            self.instance.travel_times,
            self.machine_id_map,
            self.suitable_machines_map,
            initial_scheduled_tasks=locked_tasks_map,
            min_time=start_time,
        )
