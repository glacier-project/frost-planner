# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

import matplotlib

# Force a non-interactive backend so any in-process example import (e.g.
# importing live_update.py to catch API drift) works on headless CI.
matplotlib.use("Agg", force=True)
