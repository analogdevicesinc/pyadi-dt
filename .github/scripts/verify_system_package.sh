#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <deb|rpm|osxpkg> <package-file>" >&2
    exit 2
fi

package_type=$1
package_file=$2

case "$package_type" in
    deb)
        dpkg -i "$package_file"
        package_files=$(dpkg -L python3-pyadi-dt)
        ;;
    rpm)
        rpm -i "$package_file"
        package_files=$(rpm -ql python3-pyadi-dt)
        ;;
    osxpkg)
        sudo installer -pkg "$package_file" -target /
        package_files=$(pkgutil --files com.analogdevices.python3-pyadi-dt)
        ;;
    *)
        echo "unsupported package type: $package_type" >&2
        exit 2
        ;;
esac

package_init=$(printf '%s\n' "$package_files" | grep -E '/?adidt/__init__\.py$' | head -1)
package_cli=$(printf '%s\n' "$package_files" | grep -E '/?bin/adidtc$' | head -1)
[[ "$package_init" == /* ]] || package_init="/$package_init"
[[ "$package_cli" == /* ]] || package_cli="/$package_cli"
test -f "$package_init"
test -f "$package_cli"

package_site=$(dirname "$(dirname "$package_init")")
package_test_venv="${RUNNER_TEMP:-/tmp}/adidt-package-test-venv"
package_test_python="$package_test_venv/bin/python"
test -x "$package_test_python"
(
    cd /tmp
    PYTHONPATH="$package_site" "$package_test_python" - <<'PY'
import importlib.metadata as metadata
from pathlib import Path

import adidt

assert metadata.version("pyadi-dt") == adidt.__version__
assert Path(adidt.__file__).is_file()
print(f"verified pyadi-dt {adidt.__version__} from {adidt.__file__}")
PY
    PYTHONPATH="$package_site" "$package_test_python" "$package_cli" --help >/dev/null
)