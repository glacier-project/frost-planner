import uuid
from typing import Optional, Dict
from pydantic import BaseModel, Field, model_validator


def _generate_unique_task_ids(jobs: list["Job"]) -> list["Job"]:
    """
    Make task IDs unique across all jobs by generating new UUIDs. This function
    takes a list of Job objects and reassigns all task IDs within those jobs to
    ensure uniqueness. It also updates any task dependencies to reference the
    new IDs, maintaining the dependency relationships.

    Args:
        jobs (list[Job]):
            A list of Job objects containing tasks with potentially duplicate
            IDs.
    Returns:
        list[Job]:
            The same list of Job objects with all task IDs made unique and
            dependencies updated accordingly.
    """

    id_map = {}

    for j in jobs:
        for t in j.tasks:
            task_id = str(uuid.uuid4())
            id_map[t.task_id] = task_id

            t.task_id = task_id
            t.dependencies = [id_map[dep] for dep in t.dependencies]
        j.job_id = str(uuid.uuid4())

    return jobs


def _sort_tasks(tasks: list["Task"]) -> list["Task"]:
    """
    Performs a topological sort on the given list of tasks based on their
    dependencies using the Kahn's algorithm.

    This function assumes that the input list of tasks is a directed acyclic
    graph (DAG).
    """
    # nodes = {n.task_id: n for n in tasks}
    incoming_edges = {m.task_id: [dep for dep in m.dependencies] for m in tasks}
    neighbors = {
        n.task_id: [m for m in tasks if n.task_id in m.dependencies] for n in tasks
    }

    sorted_tasks = []
    stack = [task for task in tasks if not task.dependencies]

    if not stack:
        # If there are no tasks without dependencies, the graph is not a DAG
        raise ValueError("At least one task must have no dependencies")

    while stack:
        task = stack.pop()
        sorted_tasks.append(task)

        # iterate over all outgoing edges
        for neighbor in neighbors[task.task_id]:
            # remove the edge from the graph
            incoming_edges[neighbor.task_id].remove(task.task_id)

            # add neighbor to the stack if it has no other incoming edges
            if not incoming_edges[neighbor.task_id]:
                stack.append(neighbor)

    # if there are edges left, then we have a cycle
    if len(sorted_tasks) != len(tasks):  # any(neighbors.values())
        raise ValueError("Graph is not a DAG, it contains at least one cycle")

    return sorted_tasks


class Task(BaseModel):
    """
    Represents a single, indivisible unit of work.

    A task is defined by its unique identifier, the machines that can process
    it, and its duration.

    Attributes:
        task_id (str):
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
        start_time (int
            The start time of the task.
        end_time (int):
            The end time of the task.
    """

    task_id: str = Field(
        description="A global unique identifier for the task.",
    )
    name: str = Field(
        "Unnamed Task",
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
    machines: list[str] = Field(
        default_factory=list,
        description="The identifiers of the machines that can process this task.",
    )
    priority: int = Field(
        default=1,
        gt=0,
        description="The priority of the task. Lower values indicate higher priority.",
    )
    start_time: Optional[int] = Field(
        default=None,
        ge=0,
        description="The start time of the task.",
    )
    end_time: Optional[int] = Field(
        default=None,
        ge=0,
        description="The end time of the task.",
    )

    def __str__(self) -> str:
        return (
            f"Task("
            f"task_id={self.task_id}, "
            f"name={self.name}, "
            f"processing_time={self.processing_time}, "
            f"dependencies={self.dependencies}, "
            f"priority={self.priority})"
        )

    def __repr__(self) -> str:
        return self.__str__()


class Job(BaseModel):
    """
    Represents a job consisting of multiple tasks.

    Attributes:
        job_id (str):
            A global unique identifier for the job.
        name (str):
            The name of the job.
        tasks (list[Task]):
            The tasks associated with the job.
        priority (int):
            The priority of the job. Lower values indicate higher priority.
    """

    job_id: str = Field(
        description="A global unique identifier for the job.",
    )
    name: str = Field(
        "Unnamed Job",
        description="The name of the job.",
    )
    tasks: list[Task] = Field(
        default_factory=list,
        description="The tasks associated with the job.",
    )
    priority: int = Field(
        default=1,
        gt=0,
        description="The priority of the job. Lower values indicate higher priority.",
    )

    @property
    def start_time(self) -> int:
        """
        Returns the earliest start time of all tasks in the job. If no tasks are
        present or all tasks have no start time, returns 0.

        Returns:
            int:
                The earliest start time of all tasks in the job.
        """
        start_time = None
        for t in self.tasks:
            if not t.start_time:
                continue
            if start_time is None or t.start_time < start_time:
                start_time = t.start_time
        return start_time if start_time is not None else 0

    @property
    def end_time(self) -> int:
        """
        Returns the latest end time of all tasks in the job. If no tasks are
        present or all tasks have no end time, returns 0.

        Returns:
            int:
                The latest end time of all tasks in the job.
        """
        end_time = 0
        for t in self.tasks:
            if not t.end_time:
                continue
            if t.end_time > end_time:
                end_time = t.end_time
        return end_time

    @model_validator(mode="after")
    def _validate_tasks(self) -> "Job":
        """
        Validates the tasks in the job.

        Returns:
            Job:
                The validated job instance.

        Raises:
            ValueError:
                If any task IDs are duplicated.
        """
        # Make sure all task IDs are unique.
        task_ids = set()
        for t in self.tasks:
            if t.task_id in task_ids:
                raise ValueError(
                    f"Task IDs must be unique inside a job. "
                    f"Task ID {t.task_id} is duplicated."
                )
            task_ids.add(t.task_id)
        # Perform topological sort.
        self.tasks = _sort_tasks(self.tasks)
        return self

    def __str__(self) -> str:
        return (
            f"Job("
            f"job_id={self.job_id}, "
            f"name={self.name}, "
            f"tasks={self.tasks}, "
            f"priority={self.priority})"
        )

    def __repr__(self) -> str:
        return self.__str__()


class Machine(BaseModel):
    """
    Represents a machine that can process tasks.

    Attributes:
        machine_id (str):
            A global unique identifier for the machine.
        name (str):
            The name of the machine.
        capabilities (list[str]):
            The capabilities of the machine (e.g., "cutting", "welding").
    """

    machine_id: str = Field(
        description="A global unique identifier for the machine.",
    )
    name: str = Field(
        default="Unnamed Machine",
        description="The name of the machine.",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="The capabilities of the machine.",
    )

    def __str__(self) -> str:
        return (
            f"Machine("
            f"machine_id={self.machine_id}, "
            f"name={self.name}, "
            f"capabilities={self.capabilities})"
        )

    def __repr__(self) -> str:
        return self.__str__()


class SchedulingInstance(BaseModel):
    """
    Represents a scheduling instance containing a set of jobs that need to be
    scheduled on a set of machines.

    Attributes:
        jobs (list[Job]):
            The jobs to be scheduled.
        machines (list[Machine]):
            The machines available for scheduling.
        travel_times (Dict[str, Dict[str, int]]):
            The travel times between machines (source_machine_id ->
            {destination_machine_id -> time}).
    """

    jobs: list[Job] = Field(
        default_factory=list, description="The jobs to be scheduled."
    )
    machines: list[Machine] = Field(
        default_factory=list, description="The machines available for scheduling."
    )
    travel_times: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Travel times between machines (source_machine_id "
        "-> {destination_machine_id -> time}).",
    )

    def __str__(self) -> str:
        return (
            f"SchedulingInstance("
            f"jobs={self.jobs}, "
            f"machines={self.machines}, "
            f"travel_times={self.travel_times})"
        )

    def __repr__(self) -> str:
        return self.__str__()
