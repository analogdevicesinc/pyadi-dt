#!/usr/bin/env bash
# Prepare a deterministic PATH for pyadi-dt hardware tests.
#
# GitHub self-hosted runners inherit the PATH captured when their listener
# starts. User-level tools can therefore shadow toolchain binaries (notably an
# agent CLI named `as`, which breaks Linux kernel builds expecting GNU as).

set -euo pipefail

: "${VENV_DIR:?VENV_DIR must point at the persistent hardware venv}"

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
