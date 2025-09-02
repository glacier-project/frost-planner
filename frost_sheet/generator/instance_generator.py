import random
import uuid
from dataclasses import dataclass
from frost_sheet.core.base import Job, Task, Machine, SchedulingInstance


@dataclass
class InstanceConfiguration:
    """Configuration for a job-shop scheduling instance."""

    num_jobs: int = 10
    min_job_priority: int = 1
    max_job_priority: int = 5
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
    for testing and benchmarking purposes. The generated instances can be customized
    in terms of the number of jobs, tasks, and machines.
    Jobs, tasks, and machine parameters range can be adjusted by providing an
    InstanceSpec object.

    Attributes:
        spec (InstanceSpec): The specification for the instance to generate.
        seed (int): Random seed for reproducibility.
    """

    def __init__(self, seed: int | None = None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def create_instance(
        self, configuration: InstanceConfiguration = InstanceConfiguration()
    ) -> SchedulingInstance:
        # 1. Generate all tasks first to understand their capability requirements
        all_tasks: list[Task] = []
        all_required_capabilities: set[str] = set()
        required_capability_combinations: set[tuple[str, ...]] = set() # Store sorted tuples of capabilities

        jobs: list[Job] = []
        all_possible_capabilities = [f"capability_{k}" for k in range(configuration.num_machine_capabilities)]

        for i in range(configuration.num_jobs):
            num_tasks = random.randint(
                configuration.min_tasks_per_job, configuration.max_tasks_per_job
            )
            tasks_in_job: list[Task] = []
            for j in range(num_tasks):
                processing_time = random.randint(
                    configuration.min_processing_time, configuration.max_processing_time
                )
                dependencies: list[str] = [
                    t.id
                    for t in (
                        random.sample(
                            tasks_in_job, # Use tasks_in_job for dependencies within the same job
                            k=random.randint(
                                configuration.min_task_dependencies,
                                min(
                                    len(tasks_in_job),
                                    configuration.max_task_dependencies,
                                ),
                            ),
                        )
                        if j > configuration.min_task_without_dependencies # Use min_task_without_dependencies
                        else []
                    )
                ]

                # Generate task requirements
                num_task_caps = random.randint(
                    configuration.min_task_capabilities,
                    configuration.max_task_capabilities,
                )
                # Ensure we pick from the full set of possible capabilities
                task_caps = random.sample(
                    all_possible_capabilities,
                    k=num_task_caps,
                )
                task_caps.sort() # Sort to ensure unique combinations are stored consistently
                required_capability_combinations.add(tuple(task_caps))
                all_required_capabilities.update(task_caps)

                task = Task(
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

                tasks_in_job.append(task)
                all_tasks.append(task) # Collect all tasks

            jobs.append(
                Job(
                    job_id=str(uuid.uuid4()),
                    name=f"J_{i}",
                    tasks=tasks_in_job,
                    priority=random.randint(
                        configuration.min_job_priority,
                        configuration.max_job_priority,
                    ),
                )
            )

        # 2. Generate Machines based on collected requirements
        machines: list[Machine] = []
        generated_machine_capabilities: set[tuple[str, ...]] = set()
        machine_counter = 0 # Initialize machine counter

        # Ensure a machine exists for every required capability combination
        for combo in required_capability_combinations:
            machines.append(
                Machine(
                    id=str(uuid.uuid4()),
                    name=f"M_{machine_counter}", # Use simple name
                    capabilities=list(combo),
                )
            )
            generated_machine_capabilities.add(combo)
            machine_counter += 1 # Increment counter

        # Ensure all individual capabilities are covered (if not already by combinations)
        for cap in all_possible_capabilities:
            if (cap,) not in generated_machine_capabilities: # Check if a machine with just this capability exists
                machines.append(
                    Machine(
                        id=str(uuid.uuid4()),
                        name=f"M_{machine_counter}", # Use simple name
                        capabilities=[cap],
                    )
                )
                generated_machine_capabilities.add((cap,))
                machine_counter += 1 # Increment counter

        # Add additional machines up to num_machines, with random capabilities
        # This ensures we meet the total num_machines specified in config
        num_machines_to_add = configuration.num_machines - len(machines)
        if num_machines_to_add > 0:
            for i in range(num_machines_to_add):
                num_caps_for_this_machine = random.randint(
                    configuration.min_machine_capabilities_per_machine,
                    configuration.max_machine_capabilities_per_machine,
                )
                machine_caps = random.sample(all_possible_capabilities, k=num_caps_for_this_machine)
                machines.append(
                    Machine(
                        id=str(uuid.uuid4()),
                        name=f"M_{machine_counter}", # Use simple name
                        capabilities=machine_caps,
                    )
                )
                machine_counter += 1 # Increment counter


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

        return SchedulingInstance(
            jobs=jobs, machines=machines, travel_times=travel_times
        )
