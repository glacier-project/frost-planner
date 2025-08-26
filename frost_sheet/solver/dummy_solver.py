import sys
from typing_extensions import override
from frost_sheet.solver.base_solver import BaseSolver
from frost_sheet.core.schedule import ScheduledTask
from frost_sheet.core.base import SchedulingInstance


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
        scheduled_tasks: dict[str, ScheduledTask] = {}

        tasks = [task for job in self.instance.jobs for task in job.tasks]
        for task in tasks:
            min_start_time = 0
            for dep in task.dependencies:
                start_time = scheduled_tasks[dep].end_time
                if start_time > min_start_time:
                    min_start_time = start_time

            s_intervals = self._get_machine_intervals_for_task(
                task, machine_intervals, min_start_time
            )

            machine_id = ""

            for machine_id, intervals in s_intervals.items():
                if not intervals:
                    continue

                # take the earliest starting interval
                start_time = intervals[0][0]
                curr_start_time = s_intervals[machine_id][0][0]
                if not machine_id or curr_start_time > start_time:
                    machine_id = machine_id

            assert (
                machine_id != ""
            ), f"No suitable machine found for task: {task.task_id}"

            scheduled_task = self._allocate_task(
                start_time=start_time,
                task=task,
                machine_id=machine_id,
                machine_intervals=machine_intervals,
            )
            scheduled_tasks[task.task_id] = scheduled_task

        return list(scheduled_tasks.values())
