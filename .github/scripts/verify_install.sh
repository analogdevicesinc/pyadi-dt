#!/usr/bin/env bash
set -euo pipefail

. myenv/bin/activate
package_files=$(dpkg -L python3-pyadi-dt)
printf '%s\n' "$package_files" | grep -E '/bin/adidtc$|/adidt/__init__\.py$|dist-info/METADATA$'
package_init=$(printf '%s\n' "$package_files" | grep '/adidt/__init__\.py$')
package_cli=$(printf '%s\n' "$package_files" | grep '/bin/adidtc$')
package_site=$(dirname "$(dirname "$package_init")")
(
    cd /tmp
    PYTHONPATH="$package_site" python - <<'PY'
import importlib.metadata as metadata
from pathlib import Path

import adidt

assert metadata.version("pyadi-dt") == adidt.__version__
install_path = str(Path(adidt.__file__).resolve())
assert "site-packages" in install_path or "dist-packages" in install_path
print(f"verified pyadi-dt {adidt.__version__} from {adidt.__file__}")
PY
    # The Debian artifact is intentionally thin and its post-install hook tells
    # users to provide Python dependencies. Exercise the installed launcher
    # with this dependency-complete verification environment. PYTHONPATH also
    # makes the smoke test independent of the Kuiper image's /opt/venv prefix.
    PYTHONPATH="$package_site" python "$package_cli" --help >/dev/null
)
deactivate
