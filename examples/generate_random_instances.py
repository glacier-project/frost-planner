from frost_sheet.generator.instance_generator import (
    InstanceGenerator,
    InstanceConfiguration,
    dump_configuration,
    save_instance_to_json,
)
from frost_sheet.utils import cprint
import argparse
import os

EASY_CONFIG = InstanceConfiguration(
    num_jobs=3,
    min_job_priority=1,
    max_job_priority=5,
    min_job_due_date_offset=100,
    max_job_due_date_offset=1000,
    min_tasks_per_job=2,
    max_tasks_per_job=5,
    num_machine_capabilities=5,
    num_machines=20,
    min_machine_capabilities_per_machine=1,
    max_machine_capabilities_per_machine=3,
    min_processing_time=60,
    max_processing_time=180,
    min_task_without_dependencies=1,
    max_task_without_dependencies=2,
    min_task_dependencies=1,
    max_task_dependencies=2,
    min_task_capabilities=1,
    max_task_capabilities=1,
    min_task_priority=1,
    max_task_priority=5,
    min_travel_time=1,
    max_travel_time=10,
)

MEDIUM_CONFIG = InstanceConfiguration(
    num_jobs=10,
    min_job_priority=1,
    max_job_priority=5,
    min_job_due_date_offset=100,
    max_job_due_date_offset=1000,
    min_tasks_per_job=5,
    max_tasks_per_job=8,
    num_machine_capabilities=8,
    num_machines=20,
    min_machine_capabilities_per_machine=1,
    max_machine_capabilities_per_machine=3,
    min_processing_time=60,
    max_processing_time=180,
    min_task_without_dependencies=1,
    max_task_without_dependencies=2,
    min_task_dependencies=1,
    max_task_dependencies=3,
    min_task_capabilities=1,
    max_task_capabilities=2,
    min_task_priority=1,
    max_task_priority=5,
    min_travel_time=1,
    max_travel_time=10,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate random instances")
    parser.add_argument(
        "-c",
        "--config",
        choices=["easy", "medium"],
        default="easy",
        help="Configuration level",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default="data",
        help="Output directory for the generated instances",
    )
    parser.add_argument(
        "-n",
        "--num-instances",
        type=int,
        default=1,
        help="Number of instances to generate",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.config == "easy":
        config = EASY_CONFIG
    else:
        config = MEDIUM_CONFIG

    dump_configuration(config)

    if os.path.exists(args.output_dir) and not os.path.isdir(args.output_dir):
        raise ValueError(f"Output path {args.output_dir} exists and is not a directory")

    cprint(
        f"Creating output directory [green]{args.output_dir}[/green]...",
        style="yellow",
    )

    os.makedirs(args.output_dir, exist_ok=True)

    generator = InstanceGenerator(args.seed)

    cprint(f"Generating {args.num_instances} instances...", style="yellow")

    for i in range(args.num_instances):
        # Create the scheduling instance.
        instance = generator.create_instance(config)
        # Build the final path.
        instance_path = os.path.join(args.output_dir, f"instance_{i}.json")
        # Save the instance to a JSON file.
        save_instance_to_json(instance, instance_path)
        cprint(f"  Saved instance to [green]{instance_path}[/green]", style="yellow")

    cprint("Finished generating instances.", style="yellow")


if __name__ == "__main__":
    main()
