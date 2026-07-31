#!/usr/bin/env bash
# Install the adidt package (editable, with dev extras) into a
# persistent uv-managed venv at ~/.cache/adidt-ci/adidt-venv on the
# current runner host.
#
# Reused across runs so dependency resolution is paid once per host.
# The editable install always points at the current checkout, so PR
# code changes are picked up without recreating the venv.

set -euo pipefail

VENV="$HOME/.cache/adidt-ci/adidt-venv"

export PATH="$HOME/.local/bin:$PATH"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Creating adidt venv at $VENV" >&2
    uv venv --quiet "$VENV"
fi

uv pip install --quiet --python "$VENV/bin/python" -e ".[dev]"
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
