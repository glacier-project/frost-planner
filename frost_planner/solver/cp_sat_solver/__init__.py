# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

"""CP-SAT solver package.

Public API: ``CpSatSolver``. Implementation is split across:

- ``solver`` — the ``CpSatSolver`` class itself: constructor +
  ``_allocate_tasks`` orchestration + ``_configure_solver``.
- ``_types`` — shared dataclasses (``_TaskVariables``,
  ``_AlternativeVariables``) and tiny helpers (``_safe_name``,
  ``_load_cp_model``).
- ``_model_helpers`` — CP-SAT model construction (interval/window
  bindings, break-time variable, dependency edges, capability
  cumulatives).
- ``_heuristic`` — candidate-ordering heuristic and CP-SAT hint
  application.
- ``_objective`` — objective expression and job-completion variables.
"""

from frost_planner.solver.cp_sat_solver._types import CpSatOptions
from frost_planner.solver.cp_sat_solver.solver import CpSatSolver

__all__ = ["CpSatOptions", "CpSatSolver"]
