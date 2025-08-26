import sys
from typing import override
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.core.schedule import ScheduledTask
from frost_sheet.core.base import Task, Machine 

class DummySolver(BaseSolver):
    def __init__(self, tasks: list[Task], machines: list[Machine], orizon:int = sys.maxsize) -> None:
        super().__init__(tasks, machines, orizon)

    @override
    def _allocate_tasks(self, machine_intervals: dict[str, list[tuple[int, int]]]) -> list[ScheduledTask]:
        scheduled_tasks = {}

        for task in self.tasks:
            # TODO: handle dependencies for start times
            s_intervals = self._get_machine_intervals_for_task(task, machine_intervals)
            
            machine_id = ""

            for machine_id, intervals in s_intervals.items():
                if not intervals:
                    continue

                # take the earliest starting interval
                start_time = intervals[0][0]
                curr_start_time = s_intervals[machine_id][0][0]
                if not machine_id or curr_start_time > start_time:
                    machine_id = machine_id

            assert machine_id != "", f"No suitable machine found for task: {task.task_id}"

            scheduled_task = self._allocate_task(
                start_time=start_time,
                task=task,
                machine_id=machine_id,
                machine_intervals=machine_intervals
            )
            scheduled_tasks[task.task_id] = scheduled_task

        return list(scheduled_tasks.values())