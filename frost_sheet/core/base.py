from pydantic import BaseModel, Field, model_validator


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
        start_time (int
            The start time of the task.
        end_time (int):
            The end time of the task.
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

    def __str__(self) -> str:
        return (
            f"Task("
            f"id={self.id}, "
            f"name={self.name}, "
            f"processing_time={self.processing_time}, "
            f"dependencies={self.dependencies}, "
            f"requires={self.requires}, "
            f"priority={self.priority})"
        )

    def __repr__(self) -> str:
        return self.__str__()


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
        description="The priority of the job. Lower values indicate higher priority.",
    )
    due_date: int | None = Field(
        default=None,
        ge=0,
        description="The due date for the job. If the job finishes after this date, it is considered tardy.",
    )

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
            if t.id in task_ids:
                raise ValueError(
                    f"Task IDs must be unique inside a job. "
                    f"Task ID {t.id} is duplicated."
                )
            task_ids.add(t.id)
        return self

    def __str__(self) -> str:
        return (
            f"Job("
            f"id={self.id}, "
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
        return (
            f"Machine(id={self.id}, name={self.name}, capabilities={self.capabilities})"
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

    def get_machine(self, id: str) -> Machine | None:
        """
        Retrieves a machine by its ID.

        Args:
            id (str):
                The ID of the machine to retrieve.

        Returns:
            Machine | None:
                The machine with the specified ID, or None if not found.
        """
        for machine in self.machines:
            if machine.id == id:
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
            raise ValueError(f"No travel times defined for machine {m0.id}.")
        travel_time = self.travel_times[m0.id].get(m1.id, None)
        if travel_time is None:
            raise ValueError(
                f"No travel times defined from machine {m0.id} to machine {m1.id}."
            )
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
        suitable_machines: list[Machine] = []
        for m in self.machines:
            # A machine is suitable if it has ALL required capabilities
            if all(req in m.capabilities for req in task.requires):
                suitable_machines.append(m)
        return suitable_machines

    def __str__(self) -> str:
        return (
            f"SchedulingInstance("
            f"jobs={self.jobs}, "
            f"machines={self.machines}, "
            f"travel_times={self.travel_times})"
        )

    def __repr__(self) -> str:
        return self.__str__()


def _sort_tasks(tasks: list[Task]) -> list[Task]:
    """
    Performs a topological sort on the given list of tasks based on their
    dependencies using the Kahn's algorithm.

    This function assumes that the input list of tasks is a directed acyclic
    graph (DAG).

    Args:
        tasks (list[Task]):
        The list of tasks to sort.

    Raises:
        ValueError:
            If the input list of tasks is not a DAG.

    Returns:
        list[Task]:
            The sorted list of tasks.
    """
    # nodes = {n.id: n for n in tasks}
    incoming_edges = {m.id: [dep for dep in m.dependencies] for m in tasks}
    neighbors = {n.id: [m for m in tasks if n.id in m.dependencies] for n in tasks}

    sorted_tasks: list[Task] = []
    stack = [task for task in tasks if not task.dependencies]

    if not stack:
        # If there are no tasks without dependencies, the graph is not a DAG
        raise ValueError("At least one task must have no dependencies")

    while stack:
        task = stack.pop()
        sorted_tasks.append(task)

        # iterate over all outgoing edges
        for neighbor in neighbors[task.id]:
            # remove the edge from the graph
            incoming_edges[neighbor.id].remove(task.id)

            # add neighbor to the stack if it has no other incoming edges
            if not incoming_edges[neighbor.id]:
                stack.append(neighbor)

    # if there are edges left, then we have a cycle
    if len(sorted_tasks) != len(tasks):  # any(neighbors.values())
        raise ValueError("Graph is not a DAG, it contains at least one cycle")

    return sorted_tasks
