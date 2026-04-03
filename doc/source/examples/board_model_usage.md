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

### 3. Direct construction

You can build a `BoardModel` from scratch for custom configurations:

```python
from adidt.model.board_model import BoardModel, ComponentModel, FpgaConfig, JesdLinkModel
from adidt.model.contexts import build_ad9523_1_ctx, build_ad9680_ctx
from adidt.model.renderer import BoardModelRenderer

model = BoardModel(
    name="custom_board",
    platform="zcu102",
    components=[
        ComponentModel(
            role="clock",
            part="ad9523_1",
            template="ad9523_1.tmpl",
            spi_bus="spi0",
            spi_cs=0,
            config=build_ad9523_1_ctx(cs=0, vcxo_hz=125_000_000),
        ),
        ComponentModel(
            role="adc",
            part="ad9680",
            template="ad9680.tmpl",
            spi_bus="spi0",
            spi_cs=2,
            config=build_ad9680_ctx(
                cs=2,
                clks_str="<&clk0_ad9523 13>",
                clk_names_str='"adc_clk"',
            ),
        ),
    ],
    jesd_links=[...],  # JesdLinkModel instances
    fpga_config=FpgaConfig(
        platform="zcu102", addr_cells=2,
        ps_clk_label="zynqmp_clk", ps_clk_index=71, gpio_label="gpio",
    ),
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

## Available context builders

Context builders produce the template context dicts used by the renderer.
Import them from `adidt.model.contexts`:

**Clock chips:**
- `build_ad9523_1_ctx` -- AD9523-1 (FMCDAQ2)
- `build_ad9528_ctx` -- AD9528 (FMCDAQ3)
- `build_ad9528_1_ctx` -- AD9528-1 variant (ADRV9009)
- `build_hmc7044_ctx` -- HMC7044 (AD9081, AD9084, AD9172)
- `build_hmc7044_channel_ctx` -- HMC7044 channel pre-computation

**Converters:**
- `build_ad9680_ctx` -- AD9680 ADC
- `build_ad9144_ctx` -- AD9144 DAC
- `build_ad9152_ctx` -- AD9152 DAC
- `build_ad9172_device_ctx` -- AD9172 DAC
- `build_ad9081_mxfe_ctx` -- AD9081 MxFE transceiver
- `build_adrv9009_device_ctx` -- ADRV9009 transceiver
- `build_ad9084_ctx` -- AD9084 converter
- `build_adf4382_ctx` -- ADF4382 PLL

**FPGA infrastructure:**
- `build_adxcvr_ctx` -- GT transceiver (ADXCVR)
- `build_jesd204_overlay_ctx` -- JESD204 controller overlay
- `build_tpl_core_ctx` -- TPL core (transport protocol layer)
