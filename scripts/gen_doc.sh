#!/usr/bin/env bash
# Build the Sphinx documentation under docs/build/html.
#
# Flags:
#   --serve   open the rendered index.html in the default browser when done
#   --watch   use `sphinx-autobuild` for live reload (requires it to be installed)
#
# Any other arguments are forwarded to sphinx-build / sphinx-autobuild.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

SRC=docs/source
OUT=docs/build/html

SERVE=0
WATCH=0
EXTRA=()
for arg in "$@"; do
    case "$arg" in
        --serve) SERVE=1 ;;
        --watch) WATCH=1 ;;
        *) EXTRA+=("$arg") ;;
    esac
done

if [[ "$WATCH" -eq 1 ]]; then
    uv run --with sphinx-autobuild sphinx-autobuild "$SRC" "$OUT" "${EXTRA[@]}"
    exit 0
fi

uv run sphinx-build -W --keep-going -b html "$SRC" "$OUT" "${EXTRA[@]}"

if [[ "$SERVE" -eq 1 ]]; then
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$OUT/index.html"
    elif command -v open >/dev/null 2>&1; then
        open "$OUT/index.html"
    else
        echo "Built docs at: $OUT/index.html"
    fi
fi
