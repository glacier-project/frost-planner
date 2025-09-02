from pydantic import BaseModel, ConfigDict, Field
from frost_sheet.core.base import Task, Machine, SchedulingInstance
from frost_sheet.utils import cerror


class ScheduleValidationError(Exception):
    """Custom exception for schedule validation errors."""

    pass


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

    def __str__(self) -> str:
        return f"Schedule(" f"machines={self.machines}, " f"schedule={self.mapping})"

    def __repr__(self) -> str:
        return self.__str__()


def _validate_scheduled_task_times(scheduled_task: ScheduledTask) -> bool:
    """Validates that a scheduled task's times are consistent."""
    valid = True
    if scheduled_task.start_time < 0 or scheduled_task.end_time < 0:
        cerror(
            f"Scheduled task {scheduled_task.task.id} has negative start or end time."
        )
        valid = False
    if scheduled_task.start_time > scheduled_task.end_time:
        cerror(
            f"Scheduled task {scheduled_task.task.id} has start_time "
            f"({scheduled_task.start_time}) greater than end_time "
            f"({scheduled_task.end_time})."
        )
        valid = False
    if (
        scheduled_task.end_time - scheduled_task.start_time
    ) != scheduled_task.task.processing_time:
        cerror(
            f"Scheduled task {scheduled_task.task.id} duration mismatch: "
            f"expected {scheduled_task.task.processing_time}, got "
            f"{scheduled_task.end_time - scheduled_task.start_time}."
        )
        valid = False
    return valid


def _validate_machine_assignments(schedule: Schedule) -> bool:
    """Validates that scheduled tasks are assigned to valid machines."""
    valid = True
    valid_machine_ids = {m.id for m in schedule.machines}
    for machine_id, scheduled_tasks in schedule.mapping.items():
        if machine_id not in valid_machine_ids:
            cerror(
                f"Machine ID '{machine_id}' in schedule does not exist in "
                f"provided machines."
            )
            valid = False
        for st in scheduled_tasks:
            if st.machine.id != machine_id:
                cerror(
                    f"Scheduled task {st.task.id} is assigned to "
                    f"machine '{st.machine.id}' but is listed under "
                    f"machine '{machine_id}' in the schedule."
                )
                valid = False
    return valid


def _validate_machine_task_overlaps(schedule: Schedule) -> bool:
    """Validates that tasks on the same machine do not overlap."""
    valid = True
    for machine_id, scheduled_tasks in schedule.mapping.items():
        # Sort tasks by start time to easily check for overlaps
        sorted_tasks = sorted(scheduled_tasks, key=lambda st: st.start_time)
        for i in range(len(sorted_tasks) - 1):
            task1 = sorted_tasks[i]
            task2 = sorted_tasks[i + 1]
            if task1.end_time > task2.start_time:
                cerror(
                    f"Tasks {task1.task.id} (ends {task1.end_time}) and "
                    f"{task2.task.id} (starts {task2.start_time}) overlap on "
                    f"machine '{machine_id}'."
                )
                valid = False
    return valid


def _validate_all_instance_tasks_scheduled(
    schedule: Schedule, instance: SchedulingInstance
) -> bool:
    """Validates that all tasks from the instance are present in the schedule."""
    valid = True
    instance_task_ids = {task.id for job in instance.jobs for task in job.tasks}
    scheduled_task_ids = set()
    for scheduled_tasks in schedule.mapping.values():
        for st in scheduled_tasks:
            scheduled_task_ids.add(st.task.id)

    if instance_task_ids != scheduled_task_ids:
        missing_tasks = instance_task_ids - scheduled_task_ids
        extra_tasks = scheduled_task_ids - instance_task_ids
        error_msg = "Mismatch between instance tasks and scheduled tasks."
        if missing_tasks:
            error_msg += f" Missing tasks: {missing_tasks}."
        if extra_tasks:
            error_msg += f" Extra tasks in schedule: {extra_tasks}."
        cerror(error_msg)
        valid = False
    return valid


def validate_schedule(
    schedule: Schedule,
    instance: SchedulingInstance | None = None,
) -> bool:
    """
    Performs a comprehensive validation of the given schedule.

    Args:
        schedule (Schedule):
            The schedule to validate.
        instance (SchedulingInstance, optional):
            The original scheduling instance from which the schedule was
            generated. If provided, it validates that all tasks from the
            instance are present in the schedule. Defaults to None.

    Returns:
        bool:
            True if the schedule is valid, False otherwise.
    """
    valid = True
    # Stage 1: Validate individual scheduled tasks
    for _, scheduled_tasks in schedule.mapping.items():
        for st in scheduled_tasks:
            valid &= _validate_scheduled_task_times(st)

    # Stage 2: Validate machine assignments
    valid &= _validate_machine_assignments(schedule)

    # Stage 3: Validate no overlaps on machines
    valid &= _validate_machine_task_overlaps(schedule)

    # Stage 4: Validate all instance tasks are scheduled (if instance provided)
    if instance:
        valid &= _validate_all_instance_tasks_scheduled(schedule, instance)

    return valid
