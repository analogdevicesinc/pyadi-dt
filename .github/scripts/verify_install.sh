#!/usr/bin/env bash
set -euo pipefail

. myenv/bin/activate
dpkg -L python3-adidt | grep -E '/bin/adidtc$|/adidt/__init__\.py$|dist-info/METADATA$'
(
    cd /tmp
    PYTHONPATH= python - <<'PY'
import importlib.metadata as metadata
from pathlib import Path

import adidt

assert metadata.version("adidt") == adidt.__version__
install_path = str(Path(adidt.__file__).resolve())
assert "site-packages" in install_path or "dist-packages" in install_path
print(f"verified adidt {adidt.__version__} from {adidt.__file__}")
PY
    # The Debian artifact is intentionally thin and its post-install hook tells
    # users to provide Python dependencies. Exercise the installed launcher
    # with this dependency-complete verification environment.
    PYTHONPATH= python /usr/local/bin/adidtc --help >/dev/null
)
deactivate
