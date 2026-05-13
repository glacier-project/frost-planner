#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

# Thin wrapper around `uv run tox`. Extra arguments are forwarded to tox.
#
# Examples:
#   scripts/run_tox.sh                       # run the full env list
#   scripts/run_tox.sh -e type               # only run mypy
#   scripts/run_tox.sh -e py313 -- tests/foo # pass posargs after `--`
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

uv run tox run "$@"
