# Examples

Runnable scripts live under the [`examples/`](https://github.com/glacier-project/frost-planner/tree/main/examples) directory of the repository. Each script is self-contained and uses only the public FrostPlanner API.

Run any of them with:

```bash
uv run python examples/<script>.py [args]
```

## `generate_instances.py`

Generates random Job-Shop instances from preset `InstanceConfiguration`s (easy, medium, hard) using {class}`~frost_planner.generator.instance_generator.InstanceGenerator`, then writes them as JSON to a directory.

```bash
uv run python examples/generate_instances.py -o data
```

## `solve_instance.py`

Loads a saved instance, runs one of the bundled solvers ({class}`~frost_planner.solver.dummy_solver.DummySolver`, {class}`~frost_planner.solver.stochastic_solver.StochasticSolver`, or {class}`~frost_planner.solver.genetic_solver.GeneticAlgorithmSolver`), validates the schedule, and prints makespan / lateness / total flow time.

```bash
uv run python examples/solve_instance.py -i data/instance_0.json --solver stochastic
```

## `visualize_instance.py`

Renders a scheduling instance as a Graphviz DOT diagram showing jobs, tasks, and machine-capability requirements. Useful for inspecting a problem before solving it.

```bash
uv run python examples/visualize_instance.py -i data/instance_0.json -o data/instance_0.dot
```

## `live_update.py`

Demonstrates event-driven re-scheduling: a `DynamicExecutor` advances simulated time, while new jobs arrive periodically and the solver is asked to re-optimise the remaining work in place. The Gantt chart updates live in a matplotlib window.

```bash
uv run python examples/live_update.py
```
