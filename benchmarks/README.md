# Solver Benchmarks

This folder contains the benchmark harness for comparing Frost Planner solvers.

Run a quick smoke benchmark:

```bash
uv run --group ortools python benchmarks/benchmark_solvers.py \
  --profiles tiny \
  --instances-per-profile 1 \
  --repeats 3 \
  --solvers dummy stochastic genetic cp_sat pyjobshop \
  --cp-sat-time-limit 2 \
  --cp-sat-workers 16 \
  --pyjobshop-workers 16 \
  --oracle-time-limit 5 \
  --cp-sat-travel-model pairwise \
  --machine-break-start 40 \
  --machine-break-duration 20 \
  --machine-break-repeat 120 \
  --instances-dir benchmarks/results/instances
```

By default, generated CSV results are written to
`benchmarks/results/solver_benchmark.csv`. Use `--json-output` to also write a
JSON copy.

Use `--repeats` to run each solver multiple times on the same generated
instance. Use `--instances-dir` to persist generated instances as JSON and make
before/after solver comparisons run against identical input data.
Use `--objective-*-weight` options to compare solver behavior under different
weighted objectives. Supported terms are makespan, total job flow time, number
of tardy jobs, total tardiness, total earliness, and maximum tardiness.
CP-SAT uses pairwise travel constraints by default. Use
`--cp-sat-travel-model table|pairwise|hybrid` to compare the compact travel
table formulation, pairwise reified travel constraints, and the hybrid mode
that picks per dependency edge. Use
`--cp-sat-hybrid-travel-threshold` to tune the hybrid edge-size threshold.
Use `--enable-cp-sat-dependency-bounds` and `--enable-cp-sat-load-bounds` to
compare optional CP-SAT bound-strengthening formulations.
Use `--disable-cp-sat-alternative-pruning` to compare CP-SAT against the model
that keeps all task-machine alternatives and lets constraints prove
infeasibility.
CP-SAT uses greedy schedule hints by default. Use
`--disable-cp-sat-heuristic-hints` to compare against a cold solve.
Use `--solvers pyjobshop` to compare against the reference PyJobShop
implementation. PyJobShop uses `--cp-sat-time-limit` and `--cp-sat-workers`
by default; override those with `--pyjobshop-time-limit` and
`--pyjobshop-workers` when needed. The adapter expands each Frost Planner
task-machine alternative into an optional PyJobShop task so machine-dependent
travel constraints are enforced exactly.
Use `--machine-break-start`, `--machine-break-duration`, and
`--machine-break-repeat` to benchmark solvers against deterministic machine
downtime windows.
Use `--breakable-task-ratio` and
`--breakable-task-min-processing-time` to ask the instance generator to mark a
deterministic subset of generated tasks as breakable. Persist these instances
with a dedicated `--instances-dir` because they are intentionally different
from the non-breakable profile instances.
Use `--machine-processing-time-variation` to generate per-machine processing
time overrides for each task-machine alternative.

The benchmark records runtime, validity, makespan, flow time, tardy jobs,
the number of breakable tasks, solver status, CP-SAT bounds, whether
optimality was proved, and gaps to the proven optimum or best known solution.
