#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

# Regenerate CHANGELOG.md from git history using the rules in cliff.toml.
# Requires git-cliff (fetched automatically by `uvx`).
#
# Usage:
#   scripts/gen_changelog.sh                 # preview to stdout
#   scripts/gen_changelog.sh -o CHANGELOG.md # overwrite the file
#   scripts/gen_changelog.sh --tag v0.3.0    # close out the next release
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

uvx git-cliff --config cliff.toml "$@"
