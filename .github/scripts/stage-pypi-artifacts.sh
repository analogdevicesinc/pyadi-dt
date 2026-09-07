#!/usr/bin/env bash
# Keep release manifests and other assets out of Twine's upload directory.
set -euo pipefail

source_dir=${1:?source distribution directory required}
upload_dir=${2:?empty upload directory required}
mkdir -p "$upload_dir"
if [[ -n "$(ls -A "$upload_dir")" ]]; then
    echo "PyPI staging directory must be empty: $upload_dir" >&2
    exit 1
fi

shopt -s nullglob
wheels=("$source_dir"/*.whl)
sdists=("$source_dir"/*.tar.gz)
if (( ${#wheels[@]} == 0 || ${#sdists[@]} == 0 )); then
    echo "Release requires both a wheel and a source distribution" >&2
    exit 1
fi
cp -- "${wheels[@]}" "${sdists[@]}" "$upload_dir/"
