# Board Model: Unified Device Tree Generation

The `BoardModel` is the small dataclass that sits between the two
device-tree construction paths (XSA pipeline, declarative `System`) and
the single renderer that emits DTS. It holds components, JESD links,
FPGA-side config, and metadata.

## Two ways to produce a BoardModel

### 1. XSA pipeline — from a Vivado archive

The XSA pipeline constructs a `BoardModel` internally for every
supported board. You can access it directly through the builder:

```python
from adidt.xsa.parse.topology import XsaParser
from adidt.xsa.build.builders.fmcdaq2 import FMCDAQ2Builder
from adidt.model.renderer import BoardModelRenderer

topology = XsaParser().parse("design.xsa")
cfg = {"jesd": {"rx": {"L": 4, "M": 2}, "tx": {"L": 4, "M": 2}}}

builder = FMCDAQ2Builder()
model = builder.build_model(topology, cfg, "zynqmp_clk", 71, "gpio")

for comp in model.components:
    print(f"  {comp.role}: {comp.part} on {comp.spi_bus} cs={comp.spi_cs}")

nodes = BoardModelRenderer().render(model)
```

### 2. Declarative System — typed devices

Compose a design out of `adidt.devices` classes and let `System`
assemble the `BoardModel`:

```python
import adidt

fmc = adidt.eval.ad9081_fmc()
fmc.converter.set_jesd204_mode(18, "jesd204c")
fmc.converter.adc.sample_rate = int(250e6)
fmc.converter.dac.sample_rate = int(250e6)

fpga = adidt.fpga.zcu102()

system = adidt.System(name="ad9081_zcu102", components=[fmc, fpga])
system.connect_spi(bus_index=0, primary=fpga.spi[0],
                   secondary=fmc.clock.spi, cs=0)
system.connect_spi(bus_index=1, primary=fpga.spi[1],
                   secondary=fmc.converter.spi, cs=0)
system.add_link(source=fmc.converter.adc, sink=fpga.gt[0],
                sink_reference_clock=fmc.dev_refclk,
                sink_core_clock=fmc.core_clk_rx,
                sink_sysref=fmc.dev_sysref)

model = system.to_board_model()
nodes = adidt.BoardModelRenderer().render(model)
```

## Editing a BoardModel before rendering

Either path produces the same editable dataclass. Modify anything on
it before rendering:

```python
# Replace a component's pre-rendered DTS text verbatim.
clock_comp = model.get_component("clock")
clock_comp.rendered = custom_clock_dts

# Swap the JESD link framing parameters.
rx_link = model.get_jesd_link("rx")
rx_link.link_params["L"] = 8

# Add ad-hoc nodes (fixed clocks, HSCI overlays, etc.).
model.extra_nodes.append(
    '\t&misc_clk { clock-frequency = <100000000>; };'
)

nodes = adidt.BoardModelRenderer().render(model)
```

## Supported XSA builders

| Builder | Clock | Converters |
|---------|-------|------------|
| `FMCDAQ2Builder` | AD9523-1 | AD9680 + AD9144 |
| `FMCDAQ3Builder` | AD9528 | AD9680 + AD9152 |
| `AD9172Builder` | HMC7044 | AD9172 |
| `AD9081Builder` | HMC7044 | AD9081 MxFE |
| `ADRV9009Builder` | AD9528 / AD9528-1 / HMC7044 | ADRV9009 / 9025 / 9026 / FMComms8 |
| `AD9084Builder` | HMC7044 (+ optional ADF4382) | AD9084 |

## Declarative devices available to the System API

Clock distributors and PLLs: `HMC7044`, `AD9523_1`, `AD9528`, `AD9528_1`, `ADF4382`

Converters / MxFE: `AD9081`, `AD9084`, `AD9172`, `AD9680`, `AD9144`, `AD9152`

Transceivers: `ADRV9009` (single + FMComms8 dual-chip)

FPGA JESD IP overlays: `Adxcvr`, `Jesd204Overlay`, `TplCore`

Every device class is a small pydantic model whose fields carry DT
aliases; see `api/devices` for the full pattern and how to add a new
one.

## How the renderer works

`BoardModelRenderer.render()` does three jobs:

1. Groups components by `spi_bus` and wraps each group in an
   `&spi_bus { status = "okay"; ... };` overlay.
2. For each JESD link: appends the pre-rendered DMA / TPL core /
   ADXCVR strings into the `converters` bucket and the JESD overlay
   into the direction-specific `jesd204_rx` / `jesd204_tx` bucket.
3. Appends any `model.extra_nodes` strings verbatim.

No Jinja2, no template lookups. Every string the renderer concatenates
was produced by a declarative device class in `adidt.devices`.
