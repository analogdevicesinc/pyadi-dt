# Part Layers

The part layer provides live-update abstractions for ADI clock chips and
converters. Given a JIF solver configuration (from **pyadi-jif**), the part
layer locates the matching device tree node by its `compatible` string, maps
solver fields (VCO frequency, output dividers, channel assignments) to the
corresponding DT properties, and creates or updates channel subnodes as
needed.

This is distinct from full DTS generation (see {doc}`board_class_workflow`
and {doc}`xsa`). The part layer operates on an *existing* device tree —
either on a running board's sysfs or on an SD card — and modifies only
the clock/converter nodes in place.

Configurations are consumed from JSON files or passed programmatically via
the `clock.set()` Python API.

## Supported components

### Clock Generators and Distributors

- **HMC7044**: Low-jitter clock generator with integrated VCO and 14 outputs
- **AD9523-1**: Low-jitter clock generator with distribution for high-speed converters
- **AD9528**: Dual-loop clock generator with JESD204B support and integrated VCO (part-layer implementation exists in code; supported via the BoardModel/XSA path but not yet wired into `clock.set()` for live update)
- **AD9545**: Quad-PLL, 10-output clock generator with integrated DPLL

### RF Transceivers and Data Converters

- **AD9081**: Quad 16-bit ADC + Dual 16-bit DAC with wideband MxFE transceiver
- **AD9084**: Multi-channel 16-bit ADC RF transceiver with JESD204C
- **ADRV9009**: Highly integrated dual-channel RF transceiver with JESD204B
- **AD9680**: Dual 14-bit, 1 GSPS ADC (used on DAQ2)
- **AD9144**: Quad 16-bit, 2.8 GSPS DAC (used on DAQ2)

### Evaluation Boards

- **DAQ2**: Reference design with AD9680, AD9144, and AD9523-1
- **AD9081-FMCA-EBZ**: AD9081 FMC board with HMC7044 clock (supports ZCU102, VPK180, ZC706)
- **AD9084-FMCA-EBZ**: AD9084 FMC board with HMC7044, ADF4382, and ADF4030 (supports VPK180, VCK190)
- **ADRV9009-FMCA-EBZ**: ADRV9009 FMC board with AD9528 clock (supports ZCU102, ZC706)
- **ADRV9009-PCB-Z**: ADRV9009 PCB evaluation board
- **ADRV9009-ZU11EG**: ADRV9009 with ZU11EG SoC

## CLI example with JSON from pyadi-jif

This example updates the device tree of a DAQ2 board to set the sample rate of the RX (ADC) path to 1 GSPS.

```bash
$ cat ad9523_1_jif.json
{
    "clock": {
        "m1": 3,
        "n2": 24,
        "r2": 1,
        "out_dividers": [
            2,
            128,
            8
        ],
        "output_clocks": {
            "ADC_CLK_FMC": {
                "rate": 125000000.0,
                "divider": 8
            },
            "ADC_CLK": {
                "rate": 500000000.0,
                "divider": 2
            },
            "CLKD_ADC_SYSREF": {
                "rate": 7812500.0,
                "divider": 128
            },
            "ADC_SYSREF": {
                "rate": 7812500.0,
                "divider": 128
            }
        },
        "vcxo": 125000000.0,
        "vco": 1000000000.0,
        "part": "AD9523-1"
    }
}


$ adidtc -i daq2.local -c remote_sd jif clock -f ad9523_1_jif.json
```

## Python API: `clock.set()`

The `clock` class extends `dt` with clock-chip configuration support.
Supported parts for live update: **HMC7044**, **AD9523-1**, **AD9545**.

```python
import json
from adidt import clock

# Connect to a remote board
clk = clock(dt_source="remote_sd", ip="192.168.2.1")

# Load JIF solver output
with open("ad9523_1_jif.json") as f:
    cfg = json.load(f)

# Apply clock configuration to the DT node
clk.set("AD9523-1", cfg["clock"])

# Write changes to SD card and reboot
clk.update_current_dt(reboot=True)
```

The `set()` method:

1. Looks up the clock chip's DT node by its `compatible` string
   (e.g. `adi,ad9523-1`)
2. Maps solver fields (`m1`, `n2`, `out_dividers`, `output_clocks`, etc.)
   to the corresponding DT properties
3. Creates or updates channel subnodes for each output clock

Pass `append=True` to add channels to existing subnodes instead of
replacing them.
