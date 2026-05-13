#!/usr/bin/env bash
# Thin wrapper around `uv run tox`. Extra arguments are forwarded to tox.
#
# Examples:
#   scripts/run_tox.sh                       # run the full env list
#   scripts/run_tox.sh -e type               # only run mypy
#   scripts/run_tox.sh -e py313 -- tests/foo # pass posargs after `--`
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

uv run tox run "$@"
