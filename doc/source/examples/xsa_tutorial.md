# XSA Flow Tutorials

This guide covers practical end-to-end paths to generate device trees from
Xilinx `.xsa` archives.

Use this page if you want a hands-on workflow before diving into board-specific
examples.

## Tutorial 1: Run the XSA pipeline from the CLI

### 1) Install the required tooling

```bash
pip install "adidt[xsa]"

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
