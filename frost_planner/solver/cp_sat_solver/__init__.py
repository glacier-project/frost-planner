# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""CP-SAT solver package.

Public API: ``CpSatSolver`` + ``CpSatOptions``. Implementation is
split across mixins so each submodule has one clear responsibility:

- ``solver`` — the ``CpSatSolver`` class: constructor + the
  ``_allocate_tasks`` orchestrator + ``_configure_solver``.
- ``_types`` — shared dataclasses (``CpSatOptions``,
  ``_TaskVariables``, ``_AlternativeVariables``), the public
  ``Literal`` aliases for travel/encoding/branching, and tiny
  helpers (``_safe_name``, ``_load_cp_model``).
- ``_intervals`` — interval/window construction helpers
  (``_create_break_time_var``, ``_bind_*``,
  ``_create_locked_variables``, ``_create_fixed_unavailable_intervals``).
- ``_dependencies`` — dependency-edge constraints and travel-time
  encodings (pairwise / table / hybrid; ``_machine_choices``;
  ``_table_machine_task_ids``).
- ``_cumulatives`` — per-machine NoOverlap / Cumulative and the
  redundant per-capability cumulative.
- ``_task_build`` — the per-task variable / alternative builder.
- ``_heuristic`` — candidate-ordering search + CP-SAT hint
  application.
- ``_objective`` — job-completion variables and the weighted
  objective expression.
"""

from frost_planner.solver.cp_sat_solver._types import CpSatOptions
from frost_planner.solver.cp_sat_solver.solver import CpSatSolver

__all__ = ["CpSatOptions", "CpSatSolver"]
