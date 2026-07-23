#!/usr/bin/env bash
set -euo pipefail

version=$1
architecture=$2

sudo apt update && sudo apt install -y libffi-dev python3-dev python3-venv build-essential ruby
sudo gem install fpm
python3 -m venv --system-site-packages myenv
. myenv/bin/activate
python3 -m pip install --upgrade pip
python3 - <<'PY'
import subprocess
import sys
import tomllib
from pathlib import Path

dependencies = tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]
subprocess.run([sys.executable, "-m", "pip", "install", *dependencies], check=True)
PY
deactivate

fpm -s python -t deb \
    --force --architecture "$architecture" \
    --url "https://github.com/analogdevicesinc/pyadi-dt" \
    --version "$version-1" \
    --maintainer "Engineerzone <https://ez.analog.com/sw-interface-tools>" \
    --license "EPL-2.0" \
    --no-auto-depends \
    --python-package-name-prefix python3 \
    --after-install .github/scripts/postinstall.sh \
    --description "Device tree management tools for ADI hardware
        Documentation at 
        https://analogdevicesinc.github.io/pyadi-dt/" .
