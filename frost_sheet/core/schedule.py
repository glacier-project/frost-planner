from pydantic import BaseModel, Field, model_validator

from frost_sheet.core.base import Job, Machine, Task, TaskStatus


class ScheduledTask(BaseModel):
    """
    Represents a single task that has been assigned a start and end time on a
    specific machine.

    This is a mutable data object representing a piece of the final schedule.
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

    start_time: int = Field(
        ge=0,
        description="The time at which the task begins processing.",
    )
    end_time: int = Field(
        ge=1,
        description="The time at which the task finishes processing.",
    )
    task: Task = Field(
        description="The task being scheduled.",
    )
    machine: Machine = Field(
        description="The machine this task is scheduled on.",
    )

    @model_validator(mode="after")
    def validate_scheduled_task(self) -> "ScheduledTask":
        """
        Validate the scheduled task's attributes.

        Raises:
            ValueError:
                - If end_time is less than start_time.
                - If the scheduled duration does not match the task's
                  processing_time.

        Returns:
            ScheduledTask:
                The validated scheduled task.

        """
        if self.end_time < self.start_time:
            raise ValueError("end_time must be greater than or equal to start_time")
        duration = self.end_time - self.start_time
        if duration != self.task.processing_time:
            raise ValueError(
                f"Task processing_time is {self.task.processing_time}, "
                f"but scheduled duration is {duration}"
            )
        return self

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

    def get_tasks(self) -> list[ScheduledTask]:
        """
        Get all ScheduledTasks in the schedule.

        Returns:
            list[ScheduledTask]:
                A list of all scheduled tasks in the schedule.

        """
        all_tasks: list[ScheduledTask] = []
        for tasks in self.mapping.values():
            all_tasks.extend(tasks)
        return all_tasks

    def get_machine_tasks(self, machine: Machine) -> list[ScheduledTask]:
        """
        Get all ScheduledTasks for a specific Machine.

        Args:
            machine (Machine):
                The machine to get tasks for.

        Returns:
            list[ScheduledTask]:
                A list of scheduled tasks for the machine.

        """
        return self.mapping.get(machine.id, [])

    def get_task_mapping(self, task_or_id: Task | str) -> ScheduledTask | None:
        """
        Get the ScheduledTask mapping for a specific Task.

        Args:
            task_or_id (Task | str):
                The task or its ID to get the mapping for.

        Returns:
            ScheduledTask | None:
                The scheduled task mapping or None if not found.

        """
        for scheduled_tasks in self.mapping.values():
            for st in scheduled_tasks:
                if task_or_id in (st.task.id, st.task):
                    return st
        return None

    def get_job_start_time(self, job: Job) -> float:
        """
        Calculates the earliest start time of a job from the schedule.

        Args:
            job (Job): The job to find the start time for.

        Returns:
            float:
                The earliest start time of the job, or 0.0 if no tasks are
                scheduled.

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
            job (Job):
                The job to find the end time for.

        Returns:
            float:
                The latest end time of the job, or 0.0 if no tasks are
                scheduled.

        """
        latest_end = 0.0
        for task_in_job in job.tasks:
            scheduled_task = self.get_task_mapping(task_in_job)
            if scheduled_task:
                latest_end = max(latest_end, float(scheduled_task.end_time))
        return latest_end

    def add_scheduled_task(self, scheduled_task: ScheduledTask) -> None:
        """
        Adds a ScheduledTask to the schedule.

        Args:
            scheduled_task (ScheduledTask):
                The task to add.

        """
        machine_id = scheduled_task.machine.id
        if machine_id not in self.mapping:
            self.mapping[machine_id] = []
        self.mapping[machine_id].append(scheduled_task)

    def remove_scheduled_task(self, scheduled_task: ScheduledTask) -> None:
        """
        Removes a ScheduledTask from the schedule.

        Args:
            scheduled_task (ScheduledTask):
                The task to remove.

        """
        machine_id = scheduled_task.machine.id
        if machine_id in self.mapping and scheduled_task in self.mapping[machine_id]:
            self.mapping[machine_id].remove(scheduled_task)
            if not self.mapping[machine_id]:
                del self.mapping[machine_id]

    def update_scheduled_task_machine(
        self,
        scheduled_task: ScheduledTask,
        new_machine: Machine,
    ) -> None:
        """
        Updates the machine for a ScheduledTask in the schedule.

        Args:
            scheduled_task (ScheduledTask):
                The task to update.
            new_machine (Machine):
                The new machine for the task.

        """
        # Remove from old machine's list
        self.remove_scheduled_task(scheduled_task)
        # Update the machine in the ScheduledTask object
        scheduled_task.machine = new_machine
        # Add to new machine's list
        self.add_scheduled_task(scheduled_task)

    def can_start(self, task: ScheduledTask) -> bool:
        """
        Checks if a ScheduledTask can start based on its dependencies.

        Args:
            task (ScheduledTask):
                The task to check.
        Returns:
            bool:
                True if the task can start, False otherwise.
        """
        for dependency in task.task.dependencies:
            dependency_scheduled = self.get_task_mapping(dependency)

            if dependency_scheduled is None or dependency_scheduled.task.status != TaskStatus.COMPLETED:
                return False
        return True

    def __str__(self) -> str:
        return f"Schedule(machines={self.machines}, schedule={self.mapping})"

    def __repr__(self) -> str:
        return self.__str__()
