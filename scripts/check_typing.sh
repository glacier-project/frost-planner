#!/usr/bin/env bash
# Run mypy across the source and test packages.
#
# Targets default to the in-repo packages but can be overridden via env:
#   PROJECT_SOURCE_DIR=frost_planner PROJECT_TEST_DIR=tests scripts/check_typing.sh
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

: "${PROJECT_SOURCE_DIR:=frost_planner}"
: "${PROJECT_TEST_DIR:=tests}"

uv run mypy -p "$PROJECT_SOURCE_DIR" -p "$PROJECT_TEST_DIR"
