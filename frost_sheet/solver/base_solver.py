import sys
from abc import ABC, abstractmethod
from frost_sheet.core.base import Task, Machine
from frost_sheet.core.schedule import Schedule,ScheduledTask


class BaseSolver(ABC):
    """Base class for all scheduling solvers.

    Attributes:
        tasks (list[Task]): The tasks to be scheduled.
        machines (list[Machine]): The machines available for scheduling.
        orizon (int): The time horizon for the scheduling.
    """

    def __init__(self, tasks: list[Task], machines: list[Machine], orizon:int = sys.maxsize) -> None:
        self.tasks = tasks
        self.machines = machines
        self.orizon = orizon


    def _create_machine_intervals(self) -> dict[str, list[tuple[int, int]]]:
        """Creates the initial availability intervals for each machine."""
        return {machine.machine_id: [(0, self.orizon)] for machine in self.machines}

    def _get_suitable_machines(self, task: Task) -> list[Machine]:
        """Finds all suitable machines for the given task based on its requirements.

        Args:
            task (Task): The task to find suitable machines for.

        Returns:
            list[str]: A list of machine IDs that can execute the task.
        """
        suitable_machines = []
        for m in self.machines:
            for r in task.requires:
                if r in m.capabilities:
                    suitable_machines.append(m)
                    break
        return suitable_machines

    def _set_machines_for_task(self, task: Task, machines: list[Machine] | None = None) -> None:
        """Sets the machines for a given task.

        Args:
            task (Task): The task to set machines for.
            machines (list[Machine] | None): The list of machines to assign to the task.
        """
        if machines is None:
            machines = self._get_suitable_machines(task)

        assert all([machine in self.machines for machine in machines])

        task.machines = [m.machine_id for m in machines]

    def _get_machine_intervals_for_task(self, task: Task, machine_intervals: dict[str, list[tuple[int, int]]]) -> dict[str, list[tuple[int, int]]]:
        """Gets the time intervals for a task on a specific machine.

        Args:
            task (Task): The task to get intervals for.
            machine_intervals (dict[str, list[tuple[int, int]]]): The machine intervals to get intervals from.

        Returns:
            dict[str, list[tuple[int, int]]]: A dictionary mapping machine IDs to their available time intervals for the task.
        """

        s_intervals = {}

        for machine_id, intervals in machine_intervals.items():
            if machine_id not in task.machines:
                continue

            task_start_time = task.start_time if task.start_time else 0
            task_end_time = task.end_time if task.end_time else self.orizon
            ms_intervals = []
            
            # adds all the intervals that can fit the task
            for start, end in intervals:

                # exit if the next intervals starts after the task's end time
                if start >= task_end_time:
                    break

                # skip if the interval ends before the task's start time
                if end < task_start_time:
                    continue

                # earliest start time
                start = max(start, task_start_time)
                # latest end time
                end = min(end, task_end_time)

                # check if the task can fit in the interval
                if task.processing_time > (end - start):
                    continue
                
                ms_intervals.append((start, end))
            s_intervals[machine_id] = ms_intervals

        return s_intervals
    
    def _allocate_task(self, start_time: int, task: Task, machine_id: str, machine_intervals: dict[str, list[tuple[int, int]]]) -> ScheduledTask:

        # find the selected interval
        interval_idx = -1
        for start, end in machine_intervals[machine_id]:
            if start <= start_time and end >= start_time + task.processing_time:
                interval_idx = machine_intervals[machine_id].index((start, end))
                break

        # if the interval is exactly the same as the task's time, remove it
        end_time = start_time + task.processing_time
        if start == start_time and end == end_time:
            machine_intervals[machine_id].pop(interval_idx)

        # if the start of the interval is equal to the task's start time, reduce its length
        elif start == start_time:
            machine_intervals[machine_id][interval_idx] = (end_time, end)

        # if the end of the interval is equal to the task's end time, reduce its length
        elif end == end_time:
            machine_intervals[machine_id][interval_idx] = (start, start_time)

        # if the task is contained within the interval, split the interval 
        else:
            machine_intervals[machine_id][interval_idx] = (start, start_time)
            machine_intervals[machine_id].insert(interval_idx + 1, (end_time, end))

        return ScheduledTask(
            start_time=start_time,
            end_time=start_time + task.processing_time,
            task=task,
            machine_id=machine_id
        )

    @abstractmethod
    def _allocate_tasks(self, machine_intervals: dict[str, list[tuple[int, int]]]) -> list[ScheduledTask]:
        """Allocates tasks to machines based on solver strategy.

        Args:
            machine_intervals (dict[int, list[tuple[int, int]]]): The availability intervals for each machine.
        Returns:
            list[ScheduledTask]: The scheduled tasks after allocation.
        """
        pass


    def schedule(self) -> Schedule:
        """Schedules the tasks on the machines.

        This method should be implemented by subclasses to provide specific scheduling algorithms.

        Returns:
            Schedule: The schedule created by the scheduling algorithm.
        """
        for task in self.tasks:
            if not task.machines:
                self._set_machines_for_task(task)
        machine_intervals = self._create_machine_intervals()
        scheduled_tasks = self._allocate_tasks(machine_intervals)

        # create schedule from scheduled_tasks
        machine_schedule = {
            machine.machine_id: [
                task for task in scheduled_tasks if task.machine_id == machine.machine_id
            ] for machine in self.machines
        }
        return Schedule(machines=self.machines, machine_schedule=machine_schedule)
