#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2024 the Glacier project contributors
# SPDX-License-Identifier: BSD-2-Clause

# Prepare a release: bump pyproject.toml, regenerate CHANGELOG.md, commit,
# and create an annotated tag. The release workflow at
# .github/workflows/release.yaml picks up the tag and publishes a GitHub
# Release with the matching CHANGELOG section.
#
# Usage:
#   scripts/release.sh X.Y.Z            # bump + commit + tag (no push)
#   scripts/release.sh X.Y.Z --push     # also push branch + tag
#   scripts/release.sh X.Y.Z --dry-run  # show what would happen
#   scripts/release.sh X.Y.Z --no-tag   # commit only, skip tag

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

usage() {
    echo "Usage: scripts/release.sh X.Y.Z [--push] [--no-tag] [--dry-run]" >&2
    exit 1
}

[ "$#" -ge 1 ] || usage
version="$1"
shift

if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-].+)?$ ]]; then
    echo "error: '$version' is not a valid version (expected X.Y.Z)" >&2
    exit 1
fi

push=0
make_tag=1
dry_run=0
for arg in "$@"; do
    case "$arg" in
        --push) push=1 ;;
        --no-tag) make_tag=0 ;;
        --dry-run) dry_run=1 ;;
        -h|--help) usage ;;
        *) echo "unknown flag: $arg" >&2; usage ;;
    esac
done

tag="v$version"

if git rev-parse "$tag" >/dev/null 2>&1; then
    echo "error: tag $tag already exists" >&2
    exit 1
fi

if [ "$dry_run" = "0" ] && ! git diff-index --quiet HEAD --; then
    echo "error: working tree has uncommitted changes; commit or stash them first" >&2
    exit 1
fi

# Find the most recent tag reachable from HEAD. Tags on other branches
# (e.g. v0.2.3 on main) are skipped automatically.
if prev_tag=$(git describe --tags --abbrev=0 --match='v[0-9]*' HEAD 2>/dev/null); then
    echo "Previous reachable tag: $prev_tag"
    range="$prev_tag..HEAD"
else
    echo "warning: no previous tag reachable; CHANGELOG will include all history" >&2
    range=""
fi

echo "Preparing release: $tag"

if [ "$dry_run" = "1" ]; then
    echo "[dry-run] bump pyproject.toml to $version"
    echo "[dry-run] regenerate CHANGELOG.md (${range:-full history})"
    echo "[dry-run] commit: chore(release): $tag"
    [ "$make_tag" = "1" ] && echo "[dry-run] create annotated tag $tag"
    [ "$push" = "1" ] && echo "[dry-run] push branch + tag"
    exit 0
fi

python3 - "$version" <<'PY'
import pathlib, re, sys
v = sys.argv[1]
p = pathlib.Path("pyproject.toml")
text = p.read_text()
new, count = re.subn(r'^version\s*=\s*"[^"]*"', f'version = "{v}"', text, count=1, flags=re.M)
if count == 0:
    sys.exit("error: could not find a version line in pyproject.toml")
if new != text:
    p.write_text(new)
PY

if [ -n "$range" ]; then
    uvx git-cliff --config cliff.toml --tag "$tag" "$range" --prepend CHANGELOG.md
else
    uvx git-cliff --config cliff.toml --tag "$tag" --prepend CHANGELOG.md
fi

git add pyproject.toml CHANGELOG.md
git commit -m "chore(release): $tag"

if [ "$make_tag" = "1" ]; then
    git tag -a "$tag" -m "$tag"
fi

if [ "$push" = "1" ]; then
    git push origin HEAD --follow-tags
    echo
    echo "Pushed $tag. The release workflow will publish the GitHub Release."
else
    echo
    echo "Created commit and tag $tag locally."
    echo "Push with: git push origin HEAD --follow-tags"
fi
