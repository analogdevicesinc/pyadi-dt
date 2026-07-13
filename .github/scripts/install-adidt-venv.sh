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
PYTHON_VERSION="${ADIDT_CI_PYTHON_VERSION:-3.12}"

export PATH="$HOME/.local/bin:$PATH"

if [[ -x "$VENV/bin/python" ]]; then
    current_version="$($VENV/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
else
    current_version=""
fi

if [[ "$current_version" != "$PYTHON_VERSION" ]]; then
    echo "Creating adidt Python $PYTHON_VERSION venv at $VENV" >&2
    uv python install "$PYTHON_VERSION"
    uv venv --quiet --clear --python "$PYTHON_VERSION" "$VENV"
fi

uv pip install --quiet --python "$VENV/bin/python" -e ".[dev]"

# Fail during setup rather than skipping or failing after labgrid acquisition.
for tool in pytest labgrid-client usbsdmux; do
    if [[ ! -x "$VENV/bin/$tool" ]]; then
        echo "ERROR: $tool was not installed into $VENV/bin" >&2
        exit 1
    fi
done
