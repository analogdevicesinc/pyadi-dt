#!/usr/bin/env bash
# Prepare a deterministic PATH for pyadi-dt hardware tests.
#
# GitHub self-hosted runners inherit the PATH captured when their listener
# starts. User-level tools can therefore shadow toolchain binaries (notably an
# agent CLI named `as`, which breaks Linux kernel builds expecting GNU as).

set -euo pipefail

: "${VENV_DIR:?VENV_DIR must point at the persistent hardware venv}"

# Runner-local, per-board kernel artifacts. Explicitly supplied environment
# variables can instead be used without a file. No coordinator state is changed.
if [[ -n "${BOARD:-}" && -n "${CARRIER:-}" ]]; then
    case "$BOARD-$CARRIER" in
        *[!a-zA-Z0-9_-]*) echo "Invalid hardware configuration name" >&2; return 1 2>/dev/null || exit 1 ;;
    esac
    runtime_env="${ADIDT_HARDWARE_CONFIG_DIR:-$HOME/.config/pyadi-dt/hardware}/$BOARD-$CARRIER.env"
    if [[ -f "$runtime_env" ]]; then
        source "$runtime_env"
    fi
fi

filtered_path=""
IFS=: read -r -a path_entries <<< "${PATH:-}"
for entry in "${path_entries[@]}"; do
    [[ -n "$entry" ]] || continue
    [[ "$entry" == "$HOME/.local/bin" ]] && continue
    case ":$filtered_path:" in
        *":$entry:"*) ;;
        *) filtered_path="${filtered_path:+$filtered_path:}$entry" ;;
    esac
done

export PATH="$VENV_DIR/bin:/usr/bin${filtered_path:+:$filtered_path}"

for tool in as labgrid-client pytest sdtgen; do
    resolved=$(command -v "$tool") || {
        echo "required hardware tool not found on sanitized PATH: $tool" >&2
        return 1 2>/dev/null || exit 1
    }
    printf '%s=%s\n' "$tool" "$resolved" >&2
done

if [[ "$(command -v as)" != "/usr/bin/as" ]]; then
    echo "GNU assembler shadowed after PATH sanitization: $(command -v as)" >&2
    return 1 2>/dev/null || exit 1
fi

# The coordinator's older env-yaml endpoint can infer a recovery strategy
# even when a place advertises TFTP. Render the deployment template from the
# live tags and disable SD-autoboot so the generated DTB is actually booted.
if [[ -n "${LG_ENV:-}" && -n "${LG_COORDINATOR:-}" ]]; then
    prepared_lg_env=$(mktemp "${TMPDIR:-/tmp}/adidt-lg-env-XXXXXX.yaml")
    "$VENV_DIR/bin/python" .github/scripts/prepare_labgrid_env.py \
        --env "$LG_ENV" --output "$prepared_lg_env" --coordinator "$LG_COORDINATOR"
    export LG_ENV="$prepared_lg_env"
fi
