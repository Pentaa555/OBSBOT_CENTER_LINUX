#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

source .venv/bin/activate
export PYTHONPATH="$PYTHONPATH:$DIR/bridge/build"

exec python3 -m app.main "$@"

