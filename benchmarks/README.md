# Solver Benchmarks

This folder contains the benchmark harness for comparing Frost Planner solvers.

Run a quick smoke benchmark:

```bash
uv run --group ortools python benchmarks/benchmark_solvers.py \
  --profiles tiny \
  --instances-per-profile 1 \
  --solvers dummy stochastic genetic cp_sat \
  --cp-sat-time-limit 2 \
  --oracle-time-limit 5
```

By default, generated CSV results are written to
`benchmarks/results/solver_benchmark.csv`. Use `--json-output` to also write a
JSON copy.

The benchmark records runtime, validity, makespan, flow time, tardy jobs,
solver status, CP-SAT bounds, whether optimality was proved, and gaps to the
proven optimum or best known solution.
