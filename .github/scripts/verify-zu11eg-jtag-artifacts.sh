#!/usr/bin/env bash
# Fail before acquiring tron if its fixed-JTAG payload set is incomplete or stale.
set -euo pipefail

artifact_dir="${ADIDT_ZU11EG_ARTIFACT_DIR:-$HOME/.cache/adidt-ci/zu11eg-recovery}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest="$repo_root/test/hw/config/zu11eg-jtag-artifacts.sha256"

if [[ ! -d "$artifact_dir" ]]; then
    echo "ZU11EG JTAG artifact directory not found: $artifact_dir" >&2
    exit 1
fi

(
    cd "$artifact_dir"
    sha256sum --check --strict "$manifest"
)
