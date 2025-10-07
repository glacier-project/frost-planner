import os
import subprocess
import sys

from frost_planner.core.base import SchedulingInstance
from frost_planner.utils import cerror, cprint


def export_instance_to_dot(instance: SchedulingInstance) -> str:
    """
    Convert a SchedulingInstance to a DOT representation.

    Args:
        instance (SchedulingInstance):
            The scheduling instance to convert.

    Returns:
        str:
            The DOT representation of the scheduling instance.

    """
    dot_string = "digraph G {\n"
    dot_string += "  rankdir=LR;\n"

    for job in instance.jobs:
        dot_string += f"  subgraph cluster_job_{job.name} {{\n"
        dot_string += f'    label = "Job {job.name}";\n'
        dot_string += "    style=filled;\n"
        dot_string += "    color=lightgrey;\n"

        for task in job.tasks:
            dot_string += f'    "{task.name}" [label=" {task.name}"];\n'

        dot_string += "  }\n"
    for job in instance.jobs:
        task_id_to_name = {task.id: task.name for task in job.tasks}
        for task in job.tasks:
            if task.dependencies:
                for dep_id in task.dependencies:
                    dep_name = task_id_to_name.get(dep_id)
                    if dep_name:
                        dot_string += f'  "{dep_name}" -> "{task.name}";\n'

    dot_string += "}\n"
    return dot_string


def render_dot_to_file(
    dot_string: str,
    output_path: str,
    format: str = "png",
) -> None:
    """
    Renders a DOT string to an image file using the 'dot' command (Graphviz).

    Args:
        dot_string (str):
            The DOT language string.
        output_path (str):
            The path to save the output image file.
        format (str):
            The output image format (e.g., "png", "svg", "pdf").

    """
    try:
        # Ensure the output directory exists.
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        command = ["dot", f"-T{format}", "-o", output_path]
        subprocess.run(
            command,
            input=dot_string.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        cprint(
            f"Successfully rendered graph to [green]{output_path}[/green]",
            style="yellow",
        )
    except FileNotFoundError:
        cerror(
            "Error: 'dot' command not found. Please install Graphviz.",
            file=sys.stderr,
        )
        cerror(
            "You can download it from: https://graphviz.org/download/",
            file=sys.stderr,
        )
    except subprocess.CalledProcessError as e:
        cerror(f"Error rendering graph: {e}", file=sys.stderr)
        cerror(f"Stdout: {e.stdout.decode('utf-8')}", file=sys.stderr)
        cerror(f"Stderr: {e.stderr.decode('utf-8')}", file=sys.stderr)
    except Exception as e:
        cerror(f"An unexpected error occurred: {e}", file=sys.stderr)
