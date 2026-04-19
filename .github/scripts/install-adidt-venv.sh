#!/usr/bin/env bash
# Install the adidt package (editable, with dev extras) into a
# persistent uv-managed venv at ~/.cache/adidt-ci/adidt-venv on the
# current runner host.
#
# Reused across runs so dependency resolution is paid once per host.
# The editable install always points at the current checkout, so PR
# code changes are picked up without recreating the venv.

set -euo pipefail

VENV="$HOME/.cache/adidt-ci/adidt-venv"

export PATH="$HOME/.local/bin:$PATH"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Creating adidt venv at $VENV" >&2
    uv venv --quiet "$VENV"
fi

uv pip install --quiet --python "$VENV/bin/python" -e ".[dev]"
