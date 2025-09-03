import random
import uuid
from dataclasses import dataclass
from frost_sheet.core.base import Job, Task, Machine, SchedulingInstance, _sort_tasks
from frost_sheet.utils import cprint, crule


@dataclass
class InstanceConfiguration:
    """Configuration for a job-shop scheduling instance."""

    num_jobs: int = 10
    min_job_priority: int = 1
    max_job_priority: int = 5
    min_job_due_date_offset: int = 100
    max_job_due_date_offset: int = 1000
    min_tasks_per_job: int = 2
    max_tasks_per_job: int = 5

    num_machine_capabilities: int = 5
    num_machines: int = 20
    min_machine_capabilities_per_machine: int = 1
    max_machine_capabilities_per_machine: int = 3

    min_processing_time: int = 60
    max_processing_time: int = 180
    min_task_without_dependencies: int = 1
    max_task_without_dependencies: int = 2
    min_task_dependencies: int = 1
    max_task_dependencies: int = 2

    min_task_capabilities: int = 1
    max_task_capabilities: int = 1
    min_task_priority: int = 1
    max_task_priority: int = 5

    min_travel_time: int = 1
    max_travel_time: int = 10


class InstanceGenerator:
    """Generate synthetic job-shop scheduling instances.

    This class provides methods to generate random job-shop scheduling instances
    for testing and benchmarking purposes. The generated instances can be
    customized in terms of the number of jobs, tasks, and machines. Jobs, tasks,
    and machine parameters range can be adjusted by providing an InstanceSpec
    object.

    Attributes:
        spec (InstanceSpec):
            The specification for the instance to generate.
        seed (int):
            Random seed for reproducibility.
    """

    def __init__(self, seed: int | None = None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def create_instance(
        self,
        configuration: InstanceConfiguration,
    ) -> SchedulingInstance:
        """
        Create a scheduling instance based on the provided configuration.

        Args:
            configuration (InstanceConfiguration):
                The configuration for the instance.

        Returns:
            SchedulingInstance:
                The generated scheduling instance.
        """
        jobs, required_capability_combinations, all_capabilities = (
            self._generate_jobs_and_tasks(configuration)
        )
        machines = self._generate_machines(
            configuration, required_capability_combinations, all_capabilities
        )
        travel_times = self._generate_travel_times(configuration, machines)

        return SchedulingInstance(
            jobs=jobs,
            machines=machines,
            travel_times=travel_times,
        )

    def _generate_jobs_and_tasks(
        self,
        configuration: InstanceConfiguration,
    ) -> tuple[list[Job], set[tuple[str, ...]], list[str]]:
        """
        Generate jobs and tasks for the scheduling instance.

        Args:
            configuration (InstanceConfiguration):
                The configuration for the instance.

        Returns:
            tuple[list[Job], set[tuple[str, ...]], list[str]]:
                A tuple containing the generated jobs, required capability
                combinations, and all capabilities.
        """
        # Store all required capabilities.
        all_required_capabilities: set[str] = set()
        # Store sorted tuples of capabilities.
        required_capability_combinations: set[tuple[str, ...]] = set()

        jobs: list[Job] = []
        all_capabilities = [
            f"capability_{k}" for k in range(configuration.num_machine_capabilities)
        ]
        # Build jobs and tasks.
        for i in range(configuration.num_jobs):
            # Generate the number of tasks for the job.
            num_tasks = random.randint(
                configuration.min_tasks_per_job,
                configuration.max_tasks_per_job,
            )
            # Build the task list.
            tasks: list[Task] = []
            for j in range(num_tasks):
                # Generate task processing time.
                processing_time = random.randint(
                    configuration.min_processing_time,
                    configuration.max_processing_time,
                )
                # Generate task dependencies.
                dependencies: list[str] = [
                    t.id
                    # Use tasks for dependencies within the same job.
                    for t in (
                        random.sample(
                            tasks,
                            k=random.randint(
                                configuration.min_task_dependencies,
                                min(
                                    len(tasks),
                                    configuration.max_task_dependencies,
                                ),
                            ),
                        )
                        # Use min_task_without_dependencies to ensure some tasks
                        # have no dependencies.
                        if j > configuration.min_task_without_dependencies
                        else []
                    )
                ]
                # Generate task requirements.
                num_task_caps = random.randint(
                    configuration.min_task_capabilities,
                    configuration.max_task_capabilities,
                )
                # Ensure we pick from the full set of possible capabilities
                task_caps = random.sample(
                    all_capabilities,
                    k=num_task_caps,
                )
                # Sort to ensure unique combinations are stored consistently.
                task_caps.sort()
                # Add the combination to the set.
                required_capability_combinations.add(tuple(task_caps))
                # Update all required capabilities.
                all_required_capabilities.update(task_caps)
                # Add the task to the list.
                tasks.append(
                    Task(
                        id=str(uuid.uuid4()),
                        name=f"T_{i}_{j}",
                        processing_time=processing_time,
                        dependencies=dependencies,
                        requires=task_caps,
                        priority=random.randint(
                            configuration.min_task_priority,
                            configuration.max_task_priority,
                        ),
                    )
                )
            # Perform topological sort.
            tasks = _sort_tasks(tasks)
            # Compute job processing time.
            processing_time = sum(t.processing_time for t in tasks)
            # Add the job to the list.
            jobs.append(
                Job(
                    id=str(uuid.uuid4()),
                    name=f"J_{i}",
                    tasks=tasks,
                    priority=random.randint(
                        configuration.min_job_priority,
                        configuration.max_job_priority,
                    ),
                    due_date=random.randint(
                        processing_time + configuration.min_job_due_date_offset,
                        processing_time + configuration.max_job_due_date_offset,
                    ),
                )
            )
        return jobs, required_capability_combinations, all_capabilities

    def _generate_machines(
        self,
        configuration: InstanceConfiguration,
        required_capability_combinations: set[tuple[str, ...]],
        all_capabilities: list[str],
    ) -> list[Machine]:
        """
        Generate a list of machines based on the configuration and required
        capabilities.

        Args:
            configuration (InstanceConfiguration):
                The configuration settings for the instance generator.
            required_capability_combinations (set[tuple[str, ...]]):
                A set of tuples representing the required capability
                combinations for the machines.
            all_capabilities (list[str]):
                A list of all possible capabilities that machines can have.

        Returns:
            list[Machine]:
                A list of generated machines.
        """
        machines: list[Machine] = []
        generated_machine_capabilities: set[tuple[str, ...]] = set()
        # Initialize machine counter.
        machine_counter = 0

        # Ensure a machine exists for every required capability combination
        for combo in required_capability_combinations:
            machines.append(
                Machine(
                    id=str(uuid.uuid4()),
                    name=f"M_{machine_counter}",
                    capabilities=list(combo),
                )
            )
            generated_machine_capabilities.add(combo)
            machine_counter += 1

        # Ensure all individual capabilities are covered (if not already by
        # combinations).
        for cap in all_capabilities:
            # Check if a machine with just this capability exists.
            if (cap,) not in generated_machine_capabilities:
                machines.append(
                    Machine(
                        id=str(uuid.uuid4()),
                        name=f"M_{machine_counter}",
                        capabilities=[cap],
                    )
                )
                generated_machine_capabilities.add((cap,))
                machine_counter += 1

        # Add additional machines up to num_machines, with random capabilities
        # This ensures we meet the total num_machines specified in config
        num_machines_to_add = configuration.num_machines - len(machines)
        if num_machines_to_add > 0:
            for _ in range(num_machines_to_add):
                num_caps_for_this_machine = random.randint(
                    configuration.min_machine_capabilities_per_machine,
                    configuration.max_machine_capabilities_per_machine,
                )
                machine_caps = random.sample(
                    all_capabilities, k=num_caps_for_this_machine
                )
                machines.append(
                    Machine(
                        id=str(uuid.uuid4()),
                        name=f"M_{machine_counter}",
                        capabilities=machine_caps,
                    )
                )
                machine_counter += 1
        return machines

    def _generate_travel_times(
        self,
        configuration: InstanceConfiguration,
        machines: list[Machine],
    ) -> dict[str, dict[str, int]]:
        """
        Generate travel times between machines.

        Args:
            configuration (InstanceConfiguration):
                The configuration settings for the instance generator.
            machines (list[Machine]):
                The list of generated machines.

        Returns:
            dict[str, dict[str, int]]:
                A dictionary mapping each machine ID to another dictionary
                mapping the IDs of other machines to their travel times.
        """
        travel_times: dict[str, dict[str, int]] = {}
        for m1 in machines:
            travel_times[m1.id] = {}
            for m2 in machines:
                if m1.id == m2.id:
                    continue
                travel_times[m1.id][m2.id] = random.randint(
                    configuration.min_travel_time,
                    configuration.max_travel_time,
                )
        return travel_times


def dump_configuration(config: InstanceConfiguration) -> None:
    """
    Dump the instance configuration to the console.

    Args:
        config (InstanceConfiguration): The configuration to dump.
    """
    crule("Instance Configuration", style="magenta")
    cprint(
        f"  Jobs: num_jobs={config.num_jobs}, "
        f"priority=[{config.min_job_priority}-{config.max_job_priority}], "
        f"due_date_offset=[{config.min_job_due_date_offset}-"
        f"{config.max_job_due_date_offset}]",
        style="magenta",
    )
    cprint(
        f"  Tasks per Job: [{config.min_tasks_per_job}-{config.max_tasks_per_job}]",
        style="magenta",
    )
    cprint(
        f"  Machines: num_machines={config.num_machines}, "
        f"num_capabilities={config.num_machine_capabilities}, "
        f"machine_capabilities_per_machine=["
        f"{config.min_machine_capabilities_per_machine}-"
        f"{config.max_machine_capabilities_per_machine}]",
        style="magenta",
    )
    cprint(
        f"  Processing Time: [{config.min_processing_time}-{config.max_processing_time}]",
        style="magenta",
    )
    cprint(
        f"  Task Dependencies: without_dependencies=["
        f"{config.min_task_without_dependencies}-"
        f"{config.max_task_without_dependencies}], "
        f"dependencies=[{config.min_task_dependencies}-"
        f"{config.max_task_dependencies}]",
        style="magenta",
    )
    cprint(
        f"  Task Capabilities: [{config.min_task_capabilities}-{config.max_task_capabilities}]",
        style="magenta",
    )
    cprint(
        f"  Task Priority: [{config.min_task_priority}-{config.max_task_priority}]",
        style="magenta",
    )
    cprint(
        f"  Travel Time: [{config.min_travel_time}-{config.max_travel_time}]",
        style="magenta",
    )
    crule("", style="magenta")
