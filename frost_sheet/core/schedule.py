from pydantic import BaseModel, ConfigDict, Field
from frost_sheet.core.base import Task, Machine


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

    def __str__(self) -> str:
        return f"Schedule(machines={self.machines}, schedule={self.mapping})"

    def __repr__(self) -> str:
        return self.__str__()
