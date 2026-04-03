# XSA + adijif Tutorial

This tutorial covers deriving XSA pipeline JESD/clock inputs from `pyadi-jif`
before passing them into the XSA conversion flow.

## 1) Install dependencies

```bash
pip install "adidt[xsa]"
pip install pyadi-jif[cplex]   # or pyadi-jif[gekko]
```

`pyadi-jif` is optional for pure CLI use, but required for the adijif flow
described in this page.

## 2) Build a `cfg` from adijif (quick mode)

The core idea is:

1. Create a pyadi-jif `system`.
2. Configure FPGA/VCXO/ADC/DAC objectives.
3. Extract JESD timing with `get_jesd_mode_from_params(...)`.
4. Map values to `cfg["jesd"]`.
5. Map clock labels/channels to `cfg["clock"]`.
6. Call `XsaPipeline.run()`.

### Minimal example

```python
import adijif as jif

# 1) Set up converter/FPGA context
sys = jif.system("adrv9009", "ad9528", "xilinx", vcxo=122.88e6)
sys.fpga.setup_by_dev_kit_name("zcu102")

# 2) Constrain operating mode and sample clocks
mode_rx = jif.utils.get_jesd_mode_from_params(
    sys.converter.adc, M=4, L=2, S=1, Np=16
)
mode_tx = jif.utils.get_jesd_mode_from_params(
    sys.converter.dac, M=4, L=4, S=1, Np=16
)
if not mode_rx or not mode_tx:
    raise RuntimeError("No matching JESD mode found")

sys.converter.adc.set_quick_configuration_mode(mode_rx[0]["mode"], mode_rx[0]["jesd_class"])
sys.converter.dac.set_quick_configuration_mode(mode_tx[0]["mode"], mode_tx[0]["jesd_class"])
sys.converter.adc.decimation = 8
sys.converter.adc.sample_clock = 245.76e6 / 1
sys.converter.dac.interpolation = 8
sys.converter.dac.sample_clock = 245.76e6 / 1

rx = mode_rx[0]["settings"]
tx = mode_tx[0]["settings"]
cfg = {
    "jesd": {
        "rx": {
            "F": int(rx["F"]),
            "K": int(rx["K"]),
            "M": int(rx["M"]),
            "L": int(rx["L"]),
            "Np": int(rx["Np"]),
            "S": int(rx["S"]),
        },
        "tx": {
            "F": int(tx["F"]),
            "K": int(tx["K"]),
            "M": int(tx["M"]),
            "L": int(tx["L"]),
            "Np": int(tx["Np"]),
            "S": int(tx["S"]),
        },
    },
    "clock": {
        "rx_device_clk_label": "clkgen",
        "tx_device_clk_label": "clkgen",
        "hmc7044_rx_channel": 0,
        "hmc7044_tx_channel": 0,
    },
}
```

### Optional full solve path

Some designs use `sys.solve()` to derive exact post-dividers and clock output
frequencies. This can produce richer values for downstream board-specific config:

```python
conf = sys.solve()
rx = conf.get("jesd_ADRV9009_RX", {})
tx = conf.get("jesd_ADRV9009_TX", {})
for key in ("F", "K", "M", "L", "Np", "S"):
    if key in rx:
        cfg["jesd"]["rx"][key] = int(rx[key])
    if key in tx:
        cfg["jesd"]["tx"][key] = int(tx[key])

cfg["fpga_adc"] = conf.get("fpga_adc", {})
cfg["fpga_dac"] = conf.get("fpga_dac", {})
```

When `sys.solve()` is not available or fails, fallback to quick-mode values
(`set_quick_configuration_mode` + sample-rate constraints) still produces valid
`cfg` for supported profiles.

## 3) Run XSA pipeline with the derived config

```python
from adidt.xsa.pipeline import XsaPipeline
from pathlib import Path

results = XsaPipeline().run(
    xsa_path=Path("/path/to/design.xsa"),
    cfg=cfg,
    output_dir=Path("out"),
    profile="adrv9009_zcu102",
)

print(results["merged"])
print(results["report"])
```

You can also pass `cfg` to `adidtc xsa2dt`:

```bash
adidtc xsa2dt -x /path/to/design.xsa -c cfg.json -o out/ --profile adrv9009_zcu102
```

## 4) Common adijif troubleshooting

- `ImportError: No module named adijif`  
  Install `pyadi-jif` and use a supported solver extra for your platform.
- `No matching JESD mode found`  
  Re-check `M/L/S/Np/F` constraints and converter role (`converter.adc` vs
  `converter.dac`).
- `adijif failed` / `solve()` errors  
  Use quick mode first, then tune your constraints (`sample_rate`, `fpga` setup,
  reference clocks) before rerunning `solve()`.
- `clock label not found` from XSA flow  
  Keep `cfg["clock"]` labels aligned with profile topology (for example `clkgen`,
  `hmc7044`, `clk0_ad9523`).

## 5) Example script references

- `examples/xsa/adrv9009_zcu102.py`
- `examples/xsa/fmcdaq2_zc706.py`
- `examples/xsa/fmcdaq2_zcu102.py`
- `examples/xsa/ad9083_zcu102.py`

For profile-based guidance, read the board profile docs in [xsa.rst](../xsa.rst) and
the "Using adijif (pyadi-jif) With the XSA Flow" section.
