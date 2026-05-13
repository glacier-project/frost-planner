# Quickstart

## Installation

FrostPlanner uses [`uv`](https://docs.astral.sh/uv/) for dependency and environment management. Once `uv` is installed, clone the repo and run:

```bash
uv sync
```

This creates a virtual environment in `.venv/` and installs the runtime dependencies. To include the developer toolchain (linters, type checker, tests) and the docs toolchain, use:

```bash
uv sync --all-groups
```

## Solving a Job-Shop instance

The snippet below loads a generated instance, hands it to the {class}`~frost_planner.solver.dummy_solver.DummySolver`, and renders the resulting schedule.

```python
from frost_planner.core.base import SchedulingInstance
from frost_planner.core.metrics import calculate_makespan
from frost_planner.solver.dummy_solver import DummySolver
from frost_planner.visualization.gantt import plot_gantt_chart

# 1. Load a scheduling instance
with open("data/instance_0.json", "r") as f:
    instance = SchedulingInstance.model_validate_json(f.read())

# 2. Pick a solver and solve
solver = DummySolver(instance=instance)
solution = solver.schedule()

# 3. Inspect a metric
print(f"Makespan: {calculate_makespan(solution)}")

# 4. Save a Gantt chart
plot_gantt_chart(solution, output_path="data/gantt_chart.png")
```

## Generating instances

If you don't have an instance file yet, the `examples/generate_instances.py` script ships a few preset configurations:

```bash
uv run python examples/generate_instances.py -o data
```

See [Examples](examples.md) for more end-to-end scripts.
