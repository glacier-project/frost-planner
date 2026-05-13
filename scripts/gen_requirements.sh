#!/usr/bin/env bash
# Regenerate the requirements.txt / requirements-dev.txt mirrors of uv.lock.
# Useful for environments that cannot consume the lock directly (e.g. the
# production Dockerfile, which `pip install -r requirements.txt`).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

uv export --no-hashes --no-emit-project --no-default-groups \
    --format requirements-txt -o requirements.txt
uv export --no-hashes --no-emit-project --no-default-groups --group dev \
    --format requirements-txt -o requirements-dev.txt
