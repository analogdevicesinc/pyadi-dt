# XSA Flow Tutorials

This guide covers practical end-to-end paths to generate device trees from
Xilinx `.xsa` archives.

Use this page if you want a hands-on workflow before diving into board-specific
examples.

## Tutorial 1: Run the XSA pipeline from the CLI

### 1) Install the required tooling

```bash
pip install "pyadi-dt[xsa]"

# Optional: needed for auto-deriving JESD/clock settings in example scripts
pip install pyadi-jif[cplex]   # or pyadi-jif[gekko]
```

### 2) Prepare a config file

`xsa2dt` needs a JSON config file with at least JESD and clock fields.

```json
{
  "jesd": {
    "rx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1},
    "tx": {"F": 4, "K": 32, "M": 8, "L": 4, "Np": 16, "S": 1}
  },
  "clock": {
    "rx_device_clk_label": "clkgen",
    "tx_device_clk_label": "clkgen",
    "hmc7044_rx_channel": 0,
    "hmc7044_tx_channel": 0
  }
}
```

> `clkgen`/`hmc7044` clock labels are platform- and profile-dependent. If you
> see clock-label errors, copy a built-in profile and tune this block first.

### 3) Run the converter

```bash
adidtc xsa2dt -x /path/to/design.xsa -c cfg.json -o out/
```

Useful optional flags:

- `--profile ad9081_zcu102` (force profile; omit to auto-detect)
- `--reference-dts /path/to/ref.dts` (enable parity report generation)
- `--strict-parity` (exit non-zero if required roles/links/properties are missing)
- `--timeout 180` (customize sdtgen timeout)

### 4) Collect outputs

`xsa2dt` returns these artifact paths:

- `overlay`: generated `.dtso`
- `merged`: full merged `.dts`
- `report`: HTML report (`*_report.html`) with topology + clock/jesd views
- optional: `base_dir`, `clock_dot`, `clock_d2`, `map`, `coverage`

## Tutorial 2: Use project example scripts

The `examples/xsa/` directory contains full end-to-end scripts that combine
XSA parsing, `adijif` parameter derivation, and `XsaPipeline.run()`.

Example:

```bash
python examples/xsa/adrv9009_zcu102.py --xsa /path/to/system_top.xsa
```

If you have network access and the `adi-labgrid-plugins` dependency,
you can also download a Kuiper XSA automatically:

```bash
python examples/xsa/adrv9009_zcu102.py --download-kuiper
```

Example variations by board:

- `python examples/xsa/ad9083_zcu102.py --xsa /path/to/system_top.xsa`
- `python examples/xsa/fmcdaq2_zc706.py --xsa /path/to/system_top.xsa`
- `python examples/xsa/fmcdaq2_zcu102.py --xsa /path/to/system_top.xsa`

These scripts print a final artifact summary and are a good starting point for
platform-specific defaults.

### ADRV9009 board and Talise profile files

ADRV9009 uses two distinct kinds of profile. The built-in `adrv9009_zc706`
JSON **board profile** supplies device-tree wiring. A Talise XML **filter
profile** configures the running transceiver through the driver's
`profile_config` attribute.

The example retrieves all four canonical ADRV9009 filter profiles from
[`analogdevicesinc/iio-oscilloscope`](https://github.com/analogdevicesinc/iio-oscilloscope/tree/main/filters/adrv9009).
Downloads use a reviewed commit and SHA-256 manifest rather than mutable
`main`, so changed or truncated hardware profiles fail closed.

List the available aliases:

```bash
python examples/xsa/adrv9009_profile_file.py --list-talise-profiles
```

Download and verify one profile without an XSA, Vivado, or hardware access:

```bash
python examples/xsa/adrv9009_profile_file.py \
  --talise-profile tx200-rx200-orx200 \
  --download-talise-profile \
  --output-dir build/adrv9009
```

The script prints the downloaded path and explicit target-side steps for
copying it and writing it to `profile_config`; it does not modify hardware
automatically.

The checked-in JSON override is still available to demonstrate board-profile
merging. Inspect the effective board configuration without running SDTGen:

```bash
python examples/xsa/adrv9009_profile_file.py \
  --board-profile-file examples/xsa/profiles/adrv9009_zc706_custom.json \
  --show-config
```

Run the complete XSA pipeline and retrieve the selected runtime profile in one
command:

```bash
python examples/xsa/adrv9009_profile_file.py \
  --board-profile-file my-adrv9009-board.json \
  --talise-profile tx200-rx200-orx200 \
  --xsa /path/to/system_top.xsa \
  --output-dir build/adrv9009
```

The custom JSON file only needs values that differ from the built-in board
profile. Explicit custom values win; omitted SPI assignments, GPIOs, and link
IDs continue to come from `adrv9009_zc706`. JSON keys and types are validated
before SDTGen runs. The selected Talise file remains separate and is applied
after the generated device tree has booted.

### AD9371 profiles with the corrected pyadi-jif model

The `adrv937x_zc706.py` example sends the same canonical Mykonos profile to
both tools: pyadi-jif derives and validates the primary RX, observation RX, TX,
FPGA, and shared-SYSREF intent, while pyadi-dt renders the complete profile
coefficients and places the links on the ZC706/AD9528 hardware.

Until the AD9371 model is included in a pyadi-jif release, install the reviewed
upstream revision used by CI:

```bash
pip install -r requirements/pyadi-jif-ad9371.txt
```

Inspect the profile-derived settings without an XSA, Vivado, network, or
hardware access:

```bash
python examples/xsa/adrv937x_zc706.py \
  --ad9371-profile \
    examples/xsa/profiles/ad9371_5/profile_TxBW200_ORxBW200_RxBW100.txt \
  --show-jif-config
```

The output includes the corrected Mykonos framing (`RX M=4/L=2/F=4`,
`OBS M=2/L=2/F=2`, and `TX M=4/L=4/F=2`), 14-bit converter resolution with
two control bits, profile sample rates, and the 78.125 kHz pulsed-SYSREF limit.
Add `--solve-adijif` to run the full CPLEX AD9528/FPGA solve and verify that all
three links use a common SYSREF.

Generate the DTS from an XSA using that electrical intent:

```bash
python examples/xsa/adrv937x_zc706.py \
  --ad9371-profile path/to/profile.txt \
  --xsa path/to/system_top.xsa \
  --output-dir build/adrv937x
```

## Tutorial 3: Use the Python API directly

For custom integrations (CI, scripts, internal tools), call `XsaPipeline.run()`:

```python
from adidt.xsa.pipeline import XsaPipeline
from pathlib import Path
import json

cfg = json.loads(Path("cfg.json").read_text())

result = XsaPipeline().run(
    xsa_path=Path("/path/to/design.xsa"),
    cfg=cfg,
    output_dir=Path("out"),
    emit_report=True,
    emit_clock_graphs=True,
)

for key, path in result.items():
    print(f"{key}: {path}")
```

This is the same internal flow used by `adidtc xsa2dt`.

## Tutorial 4: Validate the generated DTS

You can compile for a basic syntax check before boot-time deployment:

```bash
dtc -I dts -O dtb -o out/design.dtb out/design.dts
```

For `--reference-dts` enabled parity mode, compare the coverage report to ensure
required JESD/device roles are present before flashing a SD card.

## Related references

- [`xsa.rst`](../xsa.rst)
- [`xsa_adijif_tutorial.md`](xsa_adijif_tutorial.md)
- [`examples/xsa_ad9081_zcu102.md`](xsa_ad9081_zcu102.md)
- `examples/xsa/adrv9009_zcu102.py`
- `adidtc xsa-profiles`
- `adidtc xsa-profile-show PROFILE`
