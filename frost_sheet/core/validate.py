from frost_sheet.core.base import SchedulingInstance
from frost_sheet.utils import cerror
from frost_sheet.core.schedule import ScheduledTask, Schedule


class ScheduleValidationError(Exception):
    """Custom exception for schedule validation errors."""

    pass


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
    for st in schedule.get_tasks():
        scheduled_task_ids.add(st.task.id)

    if instance_task_ids != scheduled_task_ids:
        missing_tasks = instance_task_ids - scheduled_task_ids
        extra_tasks = scheduled_task_ids - instance_task_ids
        error_msg = "Mismatch between instance tasks and scheduled tasks."
        if missing_tasks:
            error_msg += f" Missing tasks: {list(missing_tasks)}."
        if extra_tasks:
            error_msg += f" Extra tasks in schedule: {list(extra_tasks)}."
        cerror(error_msg)
        valid = False
    return valid


def _validate_machine_capabilities(schedule: Schedule) -> bool:
    """Validates that assigned machines have the required capabilities for tasks."""
    valid = True
    for st in schedule.get_tasks():
        task_requirements = set(st.task.requires)
        machine_capabilities = set(st.machine.capabilities)
        if not task_requirements.issubset(machine_capabilities):
            missing_capabilities = task_requirements - machine_capabilities
            cerror(
                f"Task {st.task.id} requires capabilities {list(missing_capabilities)} "
                f"but machine {st.machine.id} only has {list(machine_capabilities)}."
            )
            valid = False
    return valid


def _validate_task_dependencies(
    schedule: Schedule, instance: SchedulingInstance
) -> bool:
    """Validates that task dependencies and travel times are respected."""
    valid = True
    # Create a quick lookup for scheduled tasks by their task ID
    scheduled_tasks_map: dict[str, ScheduledTask] = {}
    for st in schedule.get_tasks():
        scheduled_tasks_map[st.task.id] = st

    for st in schedule.get_tasks():
        for dep_id in st.task.dependencies:
            dependent_st = scheduled_tasks_map.get(dep_id)
            if not dependent_st:
                cerror(
                    f"Task {st.task.id} depends on task {dep_id}, "
                    f"but {dep_id} is not found in the schedule."
                )
                valid = False
                continue

            travel_time = instance.get_travel_time(dependent_st.machine, st.machine)
            if dependent_st.end_time + travel_time > st.start_time:
                cerror(
                    f"Dependency violation for task {st.task.id}: "
                    f"Dependent task {dependent_st.task.id} ends at {dependent_st.end_time} "
                    f"on machine {dependent_st.machine.id}. Travel time to {st.machine.id} "
                    f"is {travel_time}. Expected start time >= {dependent_st.end_time + travel_time}, "
                    f"but actual start time is {st.start_time}."
                )
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
            instance are present in the schedule and that dependencies are met.
            Defaults to None.

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

    # Stage 4: Validate machine capabilities (new)
    valid &= _validate_machine_capabilities(schedule)

    # Stage 5: Validate all instance tasks are scheduled (if instance provided)
    if instance:
        valid &= _validate_all_instance_tasks_scheduled(schedule, instance)
        # Stage 6: Validate task dependencies (new, requires instance)
        valid &= _validate_task_dependencies(schedule, instance)

    return valid
