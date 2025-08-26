import random
import uuid
from dataclasses import dataclass
from typing import Optional
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
    min_machine_per_capability: int = 1
    max_machine_per_capability: int = 2

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

    # min_machine_speed: float = 0.5
    # max_machine_speed: float = 2.0
    # min_setup_time: int = 0
    # max_setup_time: int = 20


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

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def create_instance(
        self, configuration: InstanceConfiguration = InstanceConfiguration()
    ) -> SchedulingInstance:
        # generate machines
        machines = []
        capabilities = []
        for i in range(configuration.num_machine_capabilities):
            capability = f"capability_{i}"
            capabilities.append(capability)

            num_machines = random.randint(
                configuration.min_machine_per_capability,
                configuration.max_machine_per_capability,
            )
            for j in range(num_machines):
                machines.append(
                    Machine(
                        machine_id=str(uuid.uuid4()),
                        name=f"machine_{i}_{j}",
                        capabilities=[capability],
                    )
                )

        # generate jobs
        jobs: list[Job] = []
        for i in range(configuration.num_jobs):
            num_tasks = random.randint(
                configuration.min_tasks_per_job, configuration.max_tasks_per_job
            )
            num_tasks_without_dependencies = random.randint(
                configuration.min_task_without_dependencies,
                configuration.max_task_without_dependencies,
            )
            tasks: list[Task] = []

            for j in range(num_tasks):
                processing_time = random.randint(
                    configuration.min_processing_time, configuration.max_processing_time
                )
                dependencies: list[str] = [
                    t.task_id
                    for t in (
                        random.sample(
                            tasks,
                            k=random.randint(
                                configuration.min_task_dependencies,
                                min(len(tasks), configuration.max_task_dependencies),
                            ),
                        )
                        if j > num_tasks_without_dependencies
                        else []
                    )
                ]

                requires = random.sample(
                    capabilities,
                    k=random.randint(
                        min(len(capabilities), configuration.min_task_capabilities),
                        min(len(capabilities), configuration.max_task_capabilities),
                    ),
                )

                task = Task(
                    task_id=str(uuid.uuid4()),
                    name=f"task_{i}_{j}",
                    processing_time=processing_time,
                    dependencies=dependencies,
                    requires=requires,
                    priority=random.randint(
                        configuration.min_task_priority, configuration.max_task_priority
                    ),
                )

                tasks.append(task)
            jobs.append(
                Job(
                    job_id=str(uuid.uuid4()),
                    name=f"job_{i}",
                    tasks=tasks,
                    priority=random.randint(
                        configuration.min_job_priority, configuration.max_job_priority
                    ),
                )
            )

        return SchedulingInstance(jobs=jobs, machines=machines)
