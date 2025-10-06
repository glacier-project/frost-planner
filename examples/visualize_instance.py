import argparse

from frost_planner.core.base import SchedulingInstance
from frost_planner.utils import cprint
from frost_planner.visualization.instance_dot_exporter import (
    export_instance_to_dot,
    render_dot_to_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize a job-shop scheduling instance using DOT language"
    )
    parser.add_argument(
        "-i",
        "--instance",
        type=str,
        default=None,
        help="Instance configuration to use",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file path. If the extension is .dot, the DOT string "
        "will be saved. Otherwise, an image will be generated "
        "(e.g., instance.png, instance.svg).",
    )
    return parser.parse_args()


def load_instance(file_path: str) -> SchedulingInstance:
    """
    Load a scheduling instance from a JSON file.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        SchedulingInstance: The loaded scheduling instance.

    """
    with open(file_path) as f:
        return SchedulingInstance.model_validate_json(f.read())


def main() -> None:
    args = parse_args()

    if args.instance:
        cprint(f"Loading instance [green]{args.instance}[/green]...", style="yellow")
        instance = load_instance(args.instance)
    else:
        cprint("No instance specified.", style="red")
        return

    cprint("Exporting instance to DOT format...", style="yellow")

    dot_string = export_instance_to_dot(instance)

    if args.output:
        output_extension = args.output.split(".")[-1].lower()
        if output_extension == "dot":
            with open(args.output, "w") as f:
                f.write(dot_string)
            cprint(f"DOT string saved to [green]{args.output}[/green]", style="yellow")
        else:
            cprint(f"Rendering DOT to [green]{args.output}[/green]...", style="yellow")
            render_dot_to_file(dot_string, args.output, output_extension)
    else:
        print(dot_string)

    cprint("Visualization complete.", style="yellow")


if __name__ == "__main__":
    main()
