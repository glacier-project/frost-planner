# 🧊 FrostSheet

A Python library for solving Flexible Job-Shop scheduling problems.

FrostSheet is a powerful and intuitive Python framework for modeling and solving scheduling instances, from classic Job-Shop and Flow-Shop problems to custom, real-world resource allocation tasks.

## 🚀 Installation

FrostSheet can be installed using `poetry`. If you don't have `poetry` installed, you can follow the instructions [here](https://python-poetry.org/docs/#installation).

Once `poetry` is set up, navigate to the project root and run:

```bash
poetry install
```

This will install all the project's dependencies.

## Frost-Sheet in Action: Solving a Simple Job-Shop Problem

Here's how to model a simple Job-Shop problem and find an optimal schedule.

First, generate an instance (if you don't have one):

```bash
poetry run python examples/generate_random_instances.py -o data
```

Then, you can use the following Python code:

```python
from frost_sheet.core.base import SchedulingInstance
from frost_sheet.solver.dummy_solver import DummySolver
from frost_sheet.visualization.gantt import plot_gantt_chart
from frost_sheet.core.metrics import calculate_makespan
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

For full API references, tutorials, and advanced usage guides, you can build the documentation locally. Navigate to the `docs/` directory and run:

```bash
make html
```

Then, open `docs/_build/html/index.html` in your web browser.

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.
