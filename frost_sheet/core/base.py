from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field, model_validator, field_validator

class TaskStatus(StrEnum):
    WAITING = "WAITING"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Task(BaseModel):
    """
    Represents a single, indivisible unit of work.

    A task is defined by its unique identifier, the machines that can process
    it, and its duration.

    Attributes:
        id (str):
            A global unique identifier for the task.
        name (str):
            The name of the task.
        processing_time (int):
            The time required to process the task.
        dependencies (list[str]):
            The identifiers of the tasks that must be completed before this task
            can start.
        requires (list[str]):
            The capabilities required to complete the task.
        machines (list[str]):
            The identifiers of the machines that can process this task.
        priority (int):
            The priority of the task. Lower values indicate higher priority.
        status (TaskStatus):
            The current status of the task.
    """

    model_config = {"frozen": True}

    id: str = Field(
        description="A global unique identifier for the task.",
    )
    name: str = Field(
        description="The name of the task.",
    )
    processing_time: int = Field(
        gt=1,
        description="The time required to process the task.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="The identifiers of the tasks that must be "
        "completed before this task can start.",
    )
    requires: list[str] = Field(
        default_factory=list,
        description="The capabilities required to complete the task.",
    )
    priority: int = Field(
        default=1,
        gt=0,
        description="The priority of the task. Lower values indicate higher priority.",
    )
    status: TaskStatus = Field(
        default=TaskStatus.WAITING,
        description="The current status of the task.",
    )

    def __str__(self) -> str:
        """
        Return string representation of the object.
        """
        return (
            f"Task("
            f"id={self.id}, "
            f"name={self.name}, "
            f"processing_time={self.processing_time}, "
            f"dependencies={self.dependencies}, "
            f"requires={self.requires}, "
            f"priority={self.priority}, "
            f"status={self.status})"
        )

    def __repr__(self) -> str:
        """
        Return repr string for the object.
        """
        return self.__str__()

    def __hash__(self) -> int:
        """
        Return hash value for the object.
        """
        return hash(
            (
                self.id,
                self.name,
                self.processing_time,
                tuple(self.dependencies),
                tuple(self.requires),
                self.priority,
                self.status,
            )
        )

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another object.
        """
        if not isinstance(other, Task):
            msg = "Comparisons must be between Task instances."
            raise TypeError(msg)
        return (
            self.id == other.id
            and self.name == other.name
            and self.processing_time == other.processing_time
            and self.dependencies == other.dependencies
            and self.requires == other.requires
            and self.priority == other.priority
            and self.status == other.status
        )


class Job(BaseModel):
    """
    Represents a job consisting of multiple tasks.

    Attributes:
        id (str):
            A global unique identifier for the job.
        name (str):
            The name of the job.
        tasks (list[Task]):
            The tasks associated with the job.
        priority (int):
            The priority of the job. Lower values indicate higher priority.

    """

    model_config = {"frozen": True}

    id: str = Field(
        description="A global unique identifier for the job.",
    )
    name: str = Field(
        description="The name of the job.",
    )
    tasks: list[Task] = Field(
        default_factory=list,
        description="The tasks associated with the job.",
    )
    priority: int = Field(
        default=1,
        gt=0,
        description="The priority of the job. Lower values indicate "
        "higher priority.",
    )
    due_date: int | None = Field(
        default=None,
        ge=0,
        description="The due date for the job. If the job finishes after "
        "this date, it is considered tardy.",
    )

    @field_validator("tasks", mode="after")
    def _validate_tasks(cls, tasks: list[Task]) -> list[Task]:
        """
        Validates the tasks in the job.

        Args:
            tasks (list[Task]):
                The list of tasks to validate.

        Returns:
            list[Task]:
                The validated list of tasks.

        Raises:
             ValueError:
                 If any task IDs are duplicated.

        """
        # Sort and verify that tasks form a DAG
        tasks = _sort_tasks(tasks)

        # Make sure all task IDs are unique.
        task_ids = set()
        for t in tasks:
            if t.id in task_ids:
                msg = "Task IDs must be unique inside a job. "
                msg += f"Task ID {t.id} is duplicated."
                raise ValueError(msg)
            task_ids.add(t.id)
        return tasks

    def __str__(self) -> str:
        """
        Return string representation of the object.
        """
        return (
            f"Job("
            f"id={self.id}, "
            f"name={self.name}, "
            f"tasks={self.tasks}, "
            f"priority={self.priority})"
        )

    def __repr__(self) -> str:
        """
        Return repr string for the object.
        """
        return self.__str__()

    def __hash__(self) -> int:
        """
        Return hash value for the object.
        """
        return hash(
            (
                self.id,
                self.name,
                tuple(t.id for t in self.tasks),
                self.priority,
                self.due_date,
            )
        )

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another object.
        """
        if not isinstance(other, Job):
            msg = "Comparisons must be between Job instances."
            raise TypeError(msg)
        return (
            self.id == other.id
            and self.name == other.name
            and self.tasks == other.tasks
            and self.priority == other.priority
            and self.due_date == other.due_date
        )


class Machine(BaseModel):
    """
    Represents a machine that can process tasks.

    Attributes:
        id (str):
            A global unique identifier for the machine.
        name (str):
            The name of the machine.
        capabilities (list[str]):
            The capabilities of the machine (e.g., "cutting", "welding").

    """

    model_config = {"frozen": True}

    id: str = Field(
        description="A global unique identifier for the machine.",
    )
    name: str = Field(
        description="The name of the machine.",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="The capabilities of the machine.",
    )

    def __str__(self) -> str:
        """
        Return string representation of the object.
        """
        return (
            f"Machine(id={self.id}, name={self.name}, capabilities={self.capabilities})"
        )

    def __repr__(self) -> str:
        """
        Return repr string for the object.
        """
        return self.__str__()

    def __hash__(self) -> int:
        """
        Return hash value for the object.
        """
        return hash(
            (
                self.id,
                self.name,
                tuple(self.capabilities),
            )
        )

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another object.
        """
        if not isinstance(other, Machine):
            msg = "Comparisons must be between Machine instances."
            raise TypeError(msg)
        return (
            self.id == other.id
            and self.name == other.name
            and self.capabilities == other.capabilities
        )


class SchedulingInstance(BaseModel):
    """
    Represents a scheduling instance containing a set of jobs that need to be
    scheduled on a set of machines.

    Attributes:
        jobs (list[Job]):
            The jobs to be scheduled.
        machines (list[Machine]):
            The machines available for scheduling.
        travel_times (dict[str, dict[str, int]]):
            The travel times between machines (source_machine_id ->
            {destination_machine_id -> time}).

    """

    model_config = {"frozen": True}

    jobs: list[Job] = Field(
        default_factory=list,
        description="The jobs to be scheduled.",
    )
    machines: list[Machine] = Field(
        default_factory=list,
        description="The machines available for scheduling.",
    )
    travel_times: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Travel times between machines (source_machine_id "
        "-> {destination_machine_id -> time}).",
    )

    def get_machine(self, machine_id: str) -> Machine | None:
        """
        Retrieves a machine by its ID.

        Args:
            machine_id (str):
                The ID of the machine to retrieve.

        Returns:
            Machine | None:
                The machine with the specified ID, or None if not found.

        """
        for machine in self.machines:
            if machine.id == machine_id:
                return machine
        return None

    def get_travel_time(self, m0: Machine, m1: Machine) -> int:
        """
        Retrieves the travel time between two machines.

        Args:
            m0 (Machine):
                The source machine.
            m1 (Machine):
                The destination machine.

        Returns:
            int:
                The travel time between the two machines, or -1 if not found.

        """
        if m0.id == m1.id:
            return 0
        if m0.id not in self.travel_times:
            msg = f"No travel times defined for machine {m0.id}."
            raise ValueError(msg)
        travel_time = self.travel_times[m0.id].get(m1.id, None)
        if travel_time is None:
            msg = f"No travel times defined from machine {m0.id} to machine {m1.id}."
            raise ValueError(msg)
        return travel_time

    def get_suitable_machines(self, task: Task) -> list[Machine]:
        """
        Finds all suitable machines for the given task based on its
         requirements.

        Args:
             task (Task):
                 The task to find suitable machines for.

        Returns:
             list[Machine]:
                 A list of machines that can execute the task.

        """
        return [
            m
            for m in self.machines
            if all(req in m.capabilities for req in task.requires)
        ]

    def __str__(self) -> str:
        """
        Return string representation of the object.
        """
        return (
            f"SchedulingInstance("
            f"jobs={self.jobs}, "
            f"machines={self.machines}, "
            f"travel_times={self.travel_times})"
        )

    def __repr__(self) -> str:
        """
        Return repr string for the object.
        """
        return self.__str__()


def _sort_tasks(tasks: list[Task]) -> list[Task]:
    """
    Performs a topological sort on the given list of tasks based on their
    dependencies using the Kahn's algorithm.

    This function assumes that the input list of tasks is a directed acyclic
    graph (DAG).

    Args:
        tasks (list[Task]): The list of tasks to sort.

    Raises:
        ValueError:
            If the input list of tasks is not a DAG.

    Returns:
        list[Task]:
            The sorted list of tasks.

    """
    if not tasks:
        return []

    incoming_edges = {m.id: list(m.dependencies) for m in tasks}
    neighbors = {n.id: [m for m in tasks if n.id in m.dependencies] for n in tasks}

    sorted_tasks: list[Task] = []
    stack = [task for task in tasks if not task.dependencies]

    if not stack:
        msg = (
            "Graph has no tasks without dependencies, indicating a cycle "
            "or an invalid DAG."
        )
        raise ValueError(msg)

    while stack:
        task = stack.pop()
        sorted_tasks.append(task)

        for neighbor in neighbors[task.id]:
            incoming_edges[neighbor.id].remove(task.id)

            if not incoming_edges[neighbor.id]:
                stack.append(neighbor)

    if len(sorted_tasks) != len(tasks):
        msg = "Graph is not a DAG, it contains at least one cycle"
        raise ValueError(msg)

    return sorted_tasks
