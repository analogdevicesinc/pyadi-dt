#!/usr/bin/env bash
# Configure host tools for pyadi-dt hardware tests in the current shell.
# Source this file so PATH changes remain visible to the pytest command:
#   source .github/scripts/setup-hw-tool-path.sh

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "ERROR: source this script instead of executing it" >&2
    exit 2
fi

VENV_DIR="${VENV_DIR:-$HOME/.cache/adidt-ci/adidt-venv}"

# Prefer the persistent CI environment. Its console scripts include pytest,
# labgrid-client, and usbsdmux installed by the project's dev extra.
export PATH="$VENV_DIR/bin:$HOME/.local/bin:$PATH"

# sdtgen is supplied either by a standalone installation already on PATH or by
# Vitis. Source the explicitly configured installation first; otherwise select
# the newest standard /tools or /opt installation available on this runner.
if ! command -v sdtgen >/dev/null 2>&1; then
    settings=""
    if [[ -n "${XILINX_VITIS:-}" && -f "$XILINX_VITIS/settings64.sh" ]]; then
        settings="$XILINX_VITIS/settings64.sh"
    else
        shopt -s nullglob
        candidates=(
            /tools/Xilinx/*/Vitis/settings64.sh
            /opt/Xilinx/*/Vitis/settings64.sh
            /opt/Xilinx/Vitis/*/settings64.sh
        )
        shopt -u nullglob
        if ((${#candidates[@]})); then
            settings="$(printf '%s\n' "${candidates[@]}" | sort -V | tail -n 1)"
        fi
    fi
    if [[ -n "$settings" ]]; then
        # Xilinx's settings script is not nounset-safe on every release.
        had_nounset=0
        [[ $- == *u* ]] && had_nounset=1 && set +u
        # shellcheck disable=SC1090
        source "$settings"
        ((had_nounset)) && set -u
        export ADIDT_VITIS_SETTINGS="$settings"
    fi
fi

# Vitis prepends its own paths, so restore the test venv to highest priority.
export PATH="$VENV_DIR/bin:$HOME/.local/bin:$PATH"
