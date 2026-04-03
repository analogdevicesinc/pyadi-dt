# BoardModel: Unified Device Tree Generation

The `BoardModel` is the core abstraction in pyadi-dt that both the XSA
pipeline and manual board-class workflows produce. It describes the complete
hardware composition of a board and can be edited before rendering to DTS.

## Three ways to create a BoardModel

### 1. From the XSA pipeline (automatic)

The XSA pipeline constructs a `BoardModel` internally for every supported
board. You can access it directly through the builder:

```python
from adidt.xsa.topology import XsaParser
from adidt.xsa.builders.fmcdaq2 import FMCDAQ2Builder
from adidt.model.renderer import BoardModelRenderer

topology = XsaParser().parse("design.xsa")
cfg = {"jesd": {"rx": {"L": 4, "M": 2}, "tx": {"L": 4, "M": 2}}}

builder = FMCDAQ2Builder()
model = builder.build_model(topology, cfg, "zynqmp_clk", 71, "gpio")

# Inspect the model
for comp in model.components:
    print(f"  {comp.role}: {comp.part} on {comp.spi_bus} cs={comp.spi_cs}")

# Render to DTS nodes
nodes = BoardModelRenderer().render(model)
```

### 2. From a board class with pyadi-jif (manual)

Board classes like `daq2` accept pyadi-jif solver output and produce
a `BoardModel`:

```python
import adijif
from adidt.boards.daq2 import daq2
from adidt.model.renderer import BoardModelRenderer

# Solve clock tree with pyadi-jif
sys = adijif.system(["ad9680", "ad9144"], "ad9523_1", "xilinx", 125e6)
sys.fpga.setup_by_dev_kit_name("zcu102")
sys.converter[0].sample_clock = 500e6
sys.converter[1].sample_clock = 500e6
conf = sys.solve()

# Map solver output to board config and build model
board = daq2(platform="zcu102")
model = board.to_board_model(conf)

# Render
nodes = BoardModelRenderer().render(model)
```

### 3. Direct construction with component factories

Build a `BoardModel` from scratch using the `components` module — no
template filenames needed:

```python
from adidt.model import BoardModel, components
from adidt.model.renderer import BoardModelRenderer

# Simple example: IMU on a Raspberry Pi
model = BoardModel(
    name="rpi5_imu",
    platform="rpi5",
    components=[
        components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
    ],
)

nodes = BoardModelRenderer().render(model)
```

For FPGA boards with clock chips and converters:

```python
model = BoardModel(
    name="custom_board",
    platform="zcu102",
    components=[
        components.ad9523_1(spi_bus="spi0", cs=0, vcxo_hz=125_000_000),
        components.ad9680(
            spi_bus="spi0", cs=2,
            clks_str="<&clk0_ad9523 13>",
            clk_names_str='"adc_clk"',
        ),
    ],
    jesd_links=[...],  # JesdLinkModel instances
)

nodes = BoardModelRenderer().render(model)
```

## Editing a BoardModel before rendering

The model is fully editable after construction. Modify any component
config, JESD parameter, or metadata before rendering:

```python
# Change clock VCXO frequency
clock = model.get_component("clock")
clock.config["vcxo_hz"] = 100_000_000

# Change JESD link parameters
rx_link = model.get_jesd_link("rx")
rx_link.link_params["L"] = 8

# Add metadata
model.metadata["config_source"] = "custom_edit"

# Render with modifications applied
nodes = BoardModelRenderer().render(model)
```

## Supported builders

| Builder | Clock | Converters | Board class |
|---------|-------|------------|-------------|
| `FMCDAQ2Builder` | AD9523-1 | AD9680 + AD9144 | `daq2` |
| `FMCDAQ3Builder` | AD9528 | AD9680 + AD9152 | -- |
| `AD9172Builder` | HMC7044 | AD9172 | -- |
| `AD9081Builder` | HMC7044 | AD9081 MxFE | `ad9081_fmc` |
| `ADRV9009Builder` | AD9528 | ADRV9009 | `adrv9009_fmc` |
| `AD9084Builder` | HMC7044 + ADF4382 | AD9084 | `ad9084_fmc` |

## Available component factories

The easiest way to add devices.  Import from `adidt.model.components`:

```python
from adidt.model import components
```

**Simple SPI:** `components.adis16495` -- ADIS16495/16497 IMU

**Clock chips:** `components.hmc7044`, `components.ad9523_1`, `components.ad9528`

**ADCs / DACs:** `components.ad9680`, `components.ad9144`, `components.ad9152`, `components.ad9172`

**Transceivers:** `components.ad9081`, `components.ad9084`

Each factory accepts `spi_bus`, `cs`, and device-specific keyword arguments.

## Context builders (advanced)

For full control, use context builders directly from `adidt.model.contexts`.
These return raw dicts for manual `ComponentModel` construction:

- **Clock chips:** `build_ad9523_1_ctx`, `build_ad9528_ctx`, `build_hmc7044_ctx`
- **Converters:** `build_ad9680_ctx`, `build_ad9144_ctx`, `build_ad9081_mxfe_ctx`, `build_adrv9009_device_ctx`
- **FPGA:** `build_adxcvr_ctx`, `build_jesd204_overlay_ctx`, `build_tpl_core_ctx`
