#!/bin/bash
# Run PetaLinux tests inside the container.
#
# Usage:
#   docker/run-petalinux-tests.sh                           # all tests (excl. full build)
#   docker/run-petalinux-tests.sh -k "test_inject"          # specific test
#   PETALINUX_FULL_BUILD=1 docker/run-petalinux-tests.sh    # include full build
#
# Required environment:
#   PETALINUX_XSA   Path to XSA file (on host; will be mounted into container)
#
# Optional environment:
#   PETALINUX_TEMPLATE   PetaLinux template (default: zynqMP)
#   PETALINUX_PROFILE    pyadi-dt profile name
#   PETALINUX_VERSION    PetaLinux version string
#   PETALINUX_FULL_BUILD Set to 1 to run the 30-60 min full build test
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="adidt-petalinux"

# Build image if it doesn't exist
if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "Building $IMAGE_NAME image..."
    docker build \
        -f "$PROJECT_DIR/docker/Dockerfile.petalinux" \
        --build-arg UID="$(id -u)" \
        --build-arg GID="$(id -g)" \
        -t "$IMAGE_NAME" \
        "$PROJECT_DIR"
fi

# Resolve XSA path
if [ -z "${PETALINUX_XSA:-}" ]; then
    echo "ERROR: PETALINUX_XSA not set. Point it at your .xsa file." >&2
    exit 1
fi
XSA_REAL="$(realpath "$PETALINUX_XSA")"
XSA_DIR="$(dirname "$XSA_REAL")"
XSA_NAME="$(basename "$XSA_REAL")"

# Forward gh token for private git deps (pyadi-build)
GH_TOKEN="${GH_TOKEN:-$(gh auth token 2>/dev/null || true)}"

# Build docker run env flags
ENV_FLAGS=(
    -e "PETALINUX_XSA=/xsa/$XSA_NAME"
)
[ -n "${GH_TOKEN:-}" ]             && ENV_FLAGS+=(-e "GH_TOKEN=$GH_TOKEN")
[ -n "${PETALINUX_TEMPLATE:-}" ]   && ENV_FLAGS+=(-e "PETALINUX_TEMPLATE=$PETALINUX_TEMPLATE")
[ -n "${PETALINUX_PROFILE:-}" ]    && ENV_FLAGS+=(-e "PETALINUX_PROFILE=$PETALINUX_PROFILE")
[ -n "${PETALINUX_VERSION:-}" ]    && ENV_FLAGS+=(-e "PETALINUX_VERSION=$PETALINUX_VERSION")
[ -n "${PETALINUX_FULL_BUILD:-}" ] && ENV_FLAGS+=(-e "PETALINUX_FULL_BUILD=$PETALINUX_FULL_BUILD")

# Default: skip full build
if [ $# -gt 0 ]; then
    PYTEST_ARGS=("$@")
else
    PYTEST_ARGS=(-k "not full_build")
fi

# Use -it only when stdin is a terminal
TTY_FLAG=""
[ -t 0 ] && TTY_FLAG="-it"

docker run --rm $TTY_FLAG \
    -v "$PROJECT_DIR:/workspace:rw" \
    -v "/tools/Xilinx:/tools/Xilinx:ro" \
    -v "$XSA_DIR:/xsa:ro" \
    "${ENV_FLAGS[@]}" \
    -w /workspace \
    "$IMAGE_NAME" \
    bash -c '
        if [ -n "${GH_TOKEN:-}" ]; then
            git config --global url."https://x-access-token:${GH_TOKEN}@github.com/".insteadOf "https://github.com/"
        fi

        # Install Python deps BEFORE sourcing PetaLinux settings.
        # PetaLinux puts its cross-compiler (x86_64-petalinux-linux-gcc)
        # on PATH which breaks native pip builds.
        uv venv /tmp/venv --quiet &&
        source /tmp/venv/bin/activate &&
        uv pip install ".[dev]" --quiet &&

        # Now source PetaLinux to get petalinux-* tools on PATH
        source /tools/Xilinx/2025.1/PetaLinux/settings.sh /tools/Xilinx/2025.1/PetaLinux >&2 || true
        # Add Vivado/bin for sdtgen (sets XILINX_VITIS and finds device_tree.tcl)
        export PATH="/tools/Xilinx/2025.1/Vivado/bin:$PATH" &&

        pytest -vs test/hw/xsa/test_petalinux_build_hw.py \
            -o addopts= \
            '"$(printf ' %q' "${PYTEST_ARGS[@]}")"'
    '
