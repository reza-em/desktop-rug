#!/usr/bin/env bash
# Run Desktop Rug from source on Linux.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/python -m desktop_rug "$@"
