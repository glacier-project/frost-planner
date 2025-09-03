from pydantic import BaseModel, ConfigDict, Field
from frost_sheet.core.base import Task, Machine, Job


class ScheduledTask(BaseModel):
    """
    Represents a single task that has been assigned a start and end time on a
    specific machine.

    This is an immutable data object representing a piece of the final schedule.
    The `order=True` argument automatically makes instances sortable by their
    attributes, starting with `start_time`.

    Attributes:
        start_time (int):
            The time at which the task begins processing.
        end_time (int):
            The time at which the task finishes processing.
        task (Task):
            The task being scheduled.
        machine_id (int):
            The identifier of the machine this task is scheduled on.
    """

    model_config = ConfigDict(frozen=True)
    start_time: int = Field(
        ge=0,
        description="The time at which the task begins processing.",
    )
    end_time: int = Field(
        ge=0,
        description="The time at which the task finishes processing.",
    )
    task: Task = Field(
        description="The task being scheduled.",
    )
    machine: Machine = Field(
        description="The machine this task is scheduled on.",
    )

    def __str__(self) -> str:
        return (
            f"ScheduledTask("
            f"start_time={self.start_time}, "
            f"end_time={self.end_time}, "
            f"task={self.task}, "
            f"machine={self.machine})"
        )

    def __repr__(self) -> str:
        return self.__str__()


class Schedule(BaseModel):
    """
    Represents a schedule consisting of multiple tasks assigned to specific
    machines.

    Attributes:
        machines (list[Machine]):
            The machines available for scheduling tasks.
        schedule (dict[int, list[ScheduledTask]]):
            A mapping of machine IDs to the tasks scheduled on them.
    """

    machines: list[Machine] = Field(
        default_factory=list,
        description="The machines available for scheduling tasks.",
    )
    mapping: dict[str, list[ScheduledTask]] = Field(
        default_factory=dict,
        description="A mapping of machine IDs to the tasks scheduled on them.",
    )

    def get_task_mapping(self, task: Task) -> ScheduledTask | None:
        """
        Get the ScheduledTask mapping for a specific Task.

        Args:
            task (Task):
                The task to get the mapping for.

        Returns:
            ScheduledTask | None:
                The scheduled task mapping or None if not found.
        """
        for scheduled_tasks in self.mapping.values():
            for st in scheduled_tasks:
                if st.task == task:
                    return st
        return None

    def get_job_start_time(self, job: Job) -> float:
        """
        Calculates the earliest start time of a job from the schedule.

        Args:
            job (Job): The job to find the start time for.

        Returns:
            float: The earliest start time of the job, or 0.0 if no tasks are scheduled.
        """
        earliest_start = float("inf")
        found_task = False
        for task_in_job in job.tasks:
            scheduled_task = self.get_task_mapping(task_in_job)
            if scheduled_task:
                earliest_start = min(earliest_start, float(scheduled_task.start_time))
                found_task = True
        return earliest_start if found_task else 0.0

    def get_job_end_time(self, job: Job) -> float:
        """
        Calculates the latest end time of a job from the schedule.

        Args:
            job (Job): The job to find the end time for.

        Returns:
            float: The latest end time of the job, or 0.0 if no tasks are scheduled.
        """
        latest_end = 0.0
        for task_in_job in job.tasks:
            scheduled_task = self.get_task_mapping(task_in_job)
            if scheduled_task:
                latest_end = max(latest_end, float(scheduled_task.end_time))
        return latest_end

    def __str__(self) -> str:
        return f"Schedule(machines={self.machines}, schedule={self.mapping})"

    def __repr__(self) -> str:
        return self.__str__()
