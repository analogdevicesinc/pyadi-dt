#!/usr/bin/env bash
# Install the adidt package (editable, with dev extras) into a
# persistent Python 3.12 uv-managed venv on the
# current runner host.
#
# Reused across runs so dependency resolution is paid once per host.
# The editable install always points at the current checkout, so PR
# code changes are picked up without recreating the venv.

set -euo pipefail

VENV="${VENV_DIR:-$HOME/.cache/adidt-ci/datax-py312-venv}"

export PATH="$HOME/.local/bin:$PATH"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Creating adidt venv at $VENV" >&2
    uv venv --quiet --python 3.12 "$VENV"
fi

"$VENV/bin/python" -c "import sys; assert sys.version_info >= (3, 11, 8), sys.version"

uv pip install --quiet --python "$VENV/bin/python" -e ".[dev]" \
    -r requirements/requirements_hw.txt
uv pip install --quiet --python "$VENV/bin/python" \
    -r requirements/pyadi-jif-ad9371.txt

# ``sdtgen`` ships with Vivado rather than the Python ``lopper`` package.
# Publish the host installation inside the persistent venv so the dynamic test
# command has one stable PATH contract on every hardware runner.
rm -f "$VENV/bin/sdtgen"
for candidate in \
    /tools/Xilinx/2025.1/Vivado/bin/sdtgen \
    /opt/Xilinx/2025.1/Vivado/bin/sdtgen; do
    if [[ -x "$candidate" ]]; then
        # Vivado's launcher resolves setupEnv.sh relative to $0, so a symlink
        # from the venv is invalid. Use a tiny wrapper that runs from bin/.
        printf '#!/usr/bin/env bash\nset -e\ncd %q\nexec ./sdtgen "$@"\n' \
            "$(dirname "$candidate")" > "$VENV/bin/sdtgen"
        chmod +x "$VENV/bin/sdtgen"
        break
    fi
done

# Fail setup before place acquisition if the persistent runner is incomplete;
# otherwise pytest can turn infrastructure defects into skip-only green jobs.
if [[ ! -x "$VENV/bin/sdtgen" ]]; then
    echo "sdtgen not found in the venv or a supported Vivado 2025.1 path" >&2
    exit 1
fi
"$VENV/bin/sdtgen" -help >/dev/null
"$VENV/bin/python" -c "import adi_lg_plugins, adijif, lopper; assert hasattr(adijif, 'ad9371')"

# CIM drives the pinned public DataX adi-linux target. Keep the verified binary
# in the hardware venv so it survives the pre-acquisition PATH sanitization.
cim_version=1.2.4
case "$(uname -m)" in
    x86_64)
        cim_target=x86_64-unknown-linux-gnu
        cim_sha256=52b0d5954ac68acc5e0b15bc419f7515037436443d7172a657c92942d0bd4f26
        ;;
    aarch64)
        cim_target=aarch64-unknown-linux-gnu
        cim_sha256=4cc4f2c15405009e8f97998895e80425c040806cb66c319de1b5a89246867b4b
        ;;
    *) echo "Unsupported CIM runner architecture: $(uname -m)" >&2; exit 1 ;;
esac
if [[ ! -x "$VENV/bin/cim" ]] || [[ "$("$VENV/bin/cim" --version | sed -n '1p')" != "cim: v$cim_version" ]]; then
    cim_temp=$(mktemp -d)
    trap 'rm -rf "$cim_temp"' EXIT
    cim_archive="cim-suite-v$cim_version-$cim_target"
    curl -fLsS --retry 3 "https://github.com/analogdevicesinc/cim/releases/download/v$cim_version/$cim_archive.tar.gz" \
        -o "$cim_temp/cim.tar.gz"
    printf '%s  %s\n' "$cim_sha256" "$cim_temp/cim.tar.gz" | sha256sum -c -
    tar -xzf "$cim_temp/cim.tar.gz" -C "$cim_temp" "$cim_archive/cim"
    install -m 755 "$cim_temp/$cim_archive/cim" "$VENV/bin/cim"
fi
"$VENV/bin/cim" --version
