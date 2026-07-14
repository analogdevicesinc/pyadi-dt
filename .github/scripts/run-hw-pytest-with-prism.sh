#!/usr/bin/env bash
# Run a hardware pytest shard with pytest-prism terminal capture enabled.
set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "usage: $0 PYTHON JUNIT_PATH PYTEST_ARGS..." >&2
    exit 2
fi

python_bin=$1
junit_path=$2
shift 2

place=${PLACE:-${LG_PLACE:-hardware}}
prism_out=${PRISM_OUT:-prism-hw-${place}}
prism_archive=${PRISM_ARCHIVE:-${prism_out}.zip}
vendor_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../vendor/pytest-prism" && pwd)
export PYTHONPATH="$vendor_root${PYTHONPATH:+:$PYTHONPATH}"

set +e
"$python_bin" -m pytest \
    -p pytest_prism.plugin \
    --prism-report \
    --prism-out="$prism_out" \
    --prism-out-overwrite \
    "$@"
pytest_rc=$?
set -e

# pytest-prism owns junit.xml so it can package the complete run. Preserve the
# reusable hardware workflow's expected JUnit path for its report and upload
# steps as well.
if [[ -f "$prism_out/junit.xml" ]]; then
    cp "$prism_out/junit.xml" "$junit_path"
else
    echo "::error::pytest-prism did not produce $prism_out/junit.xml" >&2
    if [[ $pytest_rc -eq 0 ]]; then
        pytest_rc=2
    fi
fi

# Prism's multipart ingest expects run artifacts at archive root. In
# particular, terminal.log is recognized as a run-level terminal_log artifact.
set +e
"$python_bin" - "$prism_out" "$prism_archive" <<'PY'
from pathlib import Path
import sys
import zipfile

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
if not source.is_dir():
    raise SystemExit(f"pytest-prism output directory does not exist: {source}")
with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.name != "junit.xml":
            archive.write(path, path.relative_to(source))
if not (source / "terminal.log").is_file():
    raise SystemExit(f"pytest-prism terminal capture is missing: {source / 'terminal.log'}")
PY
archive_rc=$?
set -e
if [[ $archive_rc -ne 0 && $pytest_rc -eq 0 ]]; then
    pytest_rc=$archive_rc
fi

exit "$pytest_rc"
