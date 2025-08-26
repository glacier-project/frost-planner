from frost_sheet.generator.instance_generator import (
    InstanceGenerator,
    InstanceConfiguration,
)
import argparse
import os

EASY_CONFIG = InstanceConfiguration(
    num_jobs=3,
)

MEDIUM_CONFIG = InstanceConfiguration(
    num_jobs=10,
    min_tasks_per_job=5,
    max_tasks_per_job=8,
    num_machine_capabilities=8,
    min_machine_per_capability=2,
    max_machine_per_capability=4,
    min_task_dependencies=1,
    max_task_dependencies=3,
    min_task_capabilities=1,
    max_task_capabilities=2,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate random instances")
    parser.add_argument(
        "--config",
        choices=["easy", "medium"],
        default="easy",
        help="Configuration level",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Output directory for the generated instances",
    )
    parser.add_argument(
        "--num-instances", type=int, default=1, help="Number of instances to generate"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.config == "easy":
        config = EASY_CONFIG
    else:
        config = MEDIUM_CONFIG

    if os.path.exists(args.output_dir) and not os.path.isdir(args.output_dir):
        raise ValueError(f"Output path {args.output_dir} exists and is not a directory")

    os.makedirs(args.output_dir, exist_ok=True)

    generator = InstanceGenerator(args.seed)

    for i in range(args.num_instances):
        instance = generator.create_instance(config)
        instance_path = os.path.join(args.output_dir, f"instance_{i}.json")

        with open(instance_path, "w") as f:
            f.write(
                instance.model_dump_json(
                    indent=4, exclude_defaults=True, exclude_none=True
                )
            )


if __name__ == "__main__":
    main()
