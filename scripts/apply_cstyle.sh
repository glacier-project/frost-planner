#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

# Apply code-style fixes: lint, format, complexity check.
#
# Targets default to the source and test trees but can be overridden via env:
#   PROJECT_SOURCE_DIR=frost_planner PROJECT_TEST_DIR=tests scripts/apply_cstyle.sh
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

: "${PROJECT_SOURCE_DIR:=frost_planner}"
: "${PROJECT_TEST_DIR:=tests}"

uv run ruff check --fix "$PROJECT_SOURCE_DIR" "$PROJECT_TEST_DIR"
uv run ruff format "$PROJECT_SOURCE_DIR" "$PROJECT_TEST_DIR"
uv run lizard "$PROJECT_SOURCE_DIR" "$PROJECT_TEST_DIR" -w
