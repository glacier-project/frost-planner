# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import matplotlib

# Force a non-interactive backend so the visualization tests can run on
# headless environments (CI, tox sandboxes, Docker images) where no
# display server is available.
matplotlib.use("Agg", force=True)
