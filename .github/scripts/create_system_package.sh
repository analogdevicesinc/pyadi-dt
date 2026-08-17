#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
    echo "usage: $0 <deb|rpm|osxpkg> <version> <architecture> <distro> <output-file>" >&2
    exit 2
fi

package_type=$1
version=$2
architecture=$3
distro=$4
output_file=$5

case "$package_type" in
    deb)
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            build-essential libffi-dev python3-dev python3-pip python3-venv ruby ruby-dev
        ;;
    rpm)
        dnf install -y \
            gcc libffi-devel make python3-devel python3-pip python3-rpm-generators \
            python3-virtualenv rpm-build ruby ruby-devel
        ;;
    osxpkg)
        if [[ "$(uname -s)" != "Darwin" ]]; then
            echo "osxpkg packages must be built on macOS" >&2
            exit 1
        fi
        ;;
    *)
        echo "unsupported package type: $package_type" >&2
        exit 2
        ;;
esac

gem install --no-document fpm

# Keep a dependency-complete environment outside the package source tree for the
# installed-package smoke test. System packages intentionally contain adidt
# itself; Python dependencies remain managed by the target Python environment,
# as with the existing Kuiper package.
package_test_venv="${RUNNER_TEMP:-/tmp}/adidt-package-test-venv"
rm -rf "$package_test_venv"
python3 -m venv --system-site-packages "$package_test_venv"
package_test_python="$package_test_venv/bin/python"
"$package_test_python" -m pip install --upgrade pip
"$package_test_python" - <<'PY'
import subprocess
import sys
import tomllib
from pathlib import Path

dependencies = tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]
subprocess.run([sys.executable, "-m", "pip", "install", *dependencies], check=True)
PY

mkdir -p "$(dirname "$output_file")"
output_dir=$(cd "$(dirname "$output_file")" && pwd)
output_file="$output_dir/$(basename "$output_file")"

# fpm's Python source adapter runs setuptools and writes egg-info into its input
# tree. Build from a disposable copy so container jobs (which run as root) never
# leave root-owned generated files in the checked-out source tree.
package_source=$(mktemp -d "${RUNNER_TEMP:-/tmp}/adidt-package-source.XXXXXX")
trap 'rm -rf "$package_source"' EXIT
PACKAGE_SOURCE="$package_source" python3 - <<'PY'
import os
import shutil
from pathlib import Path

ignored = shutil.ignore_patterns(
    ".git", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__",
    "*.egg-info", "build", "dist",
)
shutil.copytree(
    Path.cwd(),
    os.environ["PACKAGE_SOURCE"],
    dirs_exist_ok=True,
    ignore=ignored,
)
PY

extra_args=()
if [[ "$package_type" == "osxpkg" ]]; then
    extra_args+=(--osxpkg-identifier-prefix com.analogdevices)

    # setup-python's toolcache can place another `pkgbuild` executable ahead of
    # Apple's packaging utility. fpm resolves pkgbuild through PATH, so provide
    # a private shim that unambiguously invokes the native macOS tool.
    pkgbuild_shim="${RUNNER_TEMP:-/tmp}/adidt-package-tools"
    rm -rf "$pkgbuild_shim"
    mkdir -p "$pkgbuild_shim"
    ln -s /usr/bin/pkgbuild "$pkgbuild_shim/pkgbuild"
    export PATH="$pkgbuild_shim:$PATH"
fi

(
    cd "$package_source"
    fpm -s python -t "$package_type" \
        --force \
        --architecture "$architecture" \
        --name python3-pyadi-dt \
        --package "$output_file" \
        --url "https://github.com/analogdevicesinc/pyadi-dt" \
        --version "$version" \
        --iteration 1 \
        --maintainer "EngineerZone <https://ez.analog.com/sw-interface-tools>" \
        --license "EPL-2.0" \
        --no-auto-depends \
        --python-bin python3 \
        --python-package-name-prefix python3 \
        --description "Device tree management tools for ADI hardware ($distro build)" \
        "${extra_args[@]}" \
        .
)

test -s "$output_file"
printf 'created %s\n' "$output_file"
