# 🧊 FrostPlanner

A Python library for solving Flexible Job-Shop scheduling problems.

FrostPlanner is a powerful and intuitive Python framework for modeling and solving scheduling instances, from classic Job-Shop and Flow-Shop problems to custom, real-world resource allocation tasks.

## 🚀 Installation

FrostPlanner uses [`uv`](https://docs.astral.sh/uv/) for dependency and environment management. If you don't have `uv` installed, follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/).

Once `uv` is set up, navigate to the project root and run:

```bash
uv sync
```

This will create a virtual environment in `.venv/` and install all the project's dependencies. To also install the dev/test/docs groups, use `uv sync --all-groups`.

## FrostPlanner in Action: Solving a Simple Job-Shop Problem

Here's how to model a simple Job-Shop problem and find an optimal schedule.

First, generate an instance (if you don't have one):

```bash
uv run python examples/generate_random_instances.py -o data
```

Then, you can use the following Python code:

```python
from frost_planner.core.base import SchedulingInstance
from frost_planner.solver.dummy_solver import DummySolver
from frost_planner.visualization.gantt import plot_gantt_chart
from frost_planner.core.metrics import calculate_makespan
import os
import json

# Assuming you have a generated instance in the 'data' directory
instance_path = "data/instance_0.json" # Or any other generated instance

# 1. Load your scheduling instance
with open(instance_path, "r") as f:
    instance = SchedulingInstance.model_validate_json(f.read())

# 2. Choose and initialize a solver
solver = DummySolver(instance=instance)

# 3. Solve the scheduling problem
solution = solver.schedule()

# 4. Calculate makespan (or other metrics)
makespan = calculate_makespan(solution)
print(f"Calculated Makespan: {makespan}")

# 5. Visualize the schedule (optional)
# This will generate a Gantt chart and save it as 'data/gantt_chart.png'
plot_gantt_chart(solution, output_path="data/gantt_chart.png")
```

This will output the optimal schedule and generate a Gantt chart visualization saved to `data/gantt_chart.png`.

## 📚 Documentation

The API reference is generated automatically from source docstrings using [`sphinx-autoapi`](https://sphinx-autoapi.readthedocs.io/). To build the documentation locally, install the `docs` dependency group and run Sphinx:

```bash
uv sync --group docs
uv run sphinx-build -b html docs/source docs/build/html
```

Then, open `docs/build/html/index.html` in your web browser.

### Linting and formatting with Ruff

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and code formatting. Ruff is configured via the `pyproject.toml` file in the project root.

To run the linter and formatter, execute the following commands from the project root:

```bash
uv run ruff check --fix frost_planner examples tests
uv run ruff format frost_planner examples tests
```

### Type Checking with MyPy

This project uses [MyPy](https://mypy.readthedocs.io/en/stable/) for static type checking. MyPy is configured via the `pyproject.toml` file.

To run type checks, execute the following command from the project root:

```bash
uv run mypy frost_planner examples tests
```

## 📜 License

This project is licensed under the BSD 2-Clause License - see the LICENSE file for details.
