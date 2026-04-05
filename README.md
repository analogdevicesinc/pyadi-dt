<p align="center">
<img src="doc/source/_static/media/pyadi-dt_w_300.png" alt="pyadi-dt logo" width="300">
</p>

<h3 align="center">Device Tree Generation for Analog Devices Hardware</h3>

<p align="center">
<a href="https://github.com/analogdevicesinc/pyadi-dt/actions/workflows/build_pip.yml"><img src="https://github.com/analogdevicesinc/pyadi-dt/actions/workflows/build_pip.yml/badge.svg" alt="CI"></a>
<a href="https://analogdevicesinc.github.io/pyadi-dt/"><img src="https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg" alt="Docs"></a>
<a href="https://github.com/analogdevicesinc/pyadi-dt/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-EPL--2.0-green.svg" alt="License"></a>
<a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
</p>

---

**pyadi-dt** is a Python library and CLI for generating, inspecting, and managing Linux device trees for Analog Devices data converters, clock ICs, RF transceivers, and FPGA-based JESD204 data paths.

## Key Features

- **XSA-to-DTS pipeline** — Generate device trees from Vivado `.xsa` archives using built-in board profiles
- **BoardModel API** — Build, edit, and render device tree overlays programmatically
- **88 Kuiper boards** — Full manifest of ADI Kuiper 2023-R2 supported boards
- **RPi support** — Generate overlays for ADI sensors on Raspberry Pi (ADIS16495, ADXL345, AD7124, etc.)
- **15 board classes** — DAQ2, AD9081–AD9084, ADRV9002–ADRV9025, ADRV937x, ADRV9361-Z7035, ADRV9364-Z7020, FMComms, RPi
- **Component factories** — Pre-configured factories for 12+ ADI devices
- **Visualization** — Interactive HTML reports, clock-tree diagrams (DOT/D2), DTS linter
- **Hardware validated** — FMCDAQ2, FMCDAQ3, AD9081, ADRV9009 on ZCU102

## Quick Install

```bash
pip install git+https://github.com/analogdevicesinc/pyadi-dt.git
```

With XSA pipeline support (requires Vivado `sdtgen`):

```bash
pip install "git+https://github.com/analogdevicesinc/pyadi-dt.git#egg=adidt[xsa]"
```

## Quick Examples

### Generate a DTS from an XSA file

```bash
adidtc xsa2dt -x design.xsa --profile ad9081_zcu102 -o out/
```

### Generate a DTS from Python (BoardModel API)

```python
from adidt.model import BoardModel, components
from adidt.model.renderer import BoardModelRenderer

model = BoardModel(
    name="rpi5_imu",
    platform="rpi5",
    components=[
        components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
    ],
)
nodes = BoardModelRenderer().render(model)
```

### Generate a DTS for an FPGA board

```python
from adidt.boards.daq2 import daq2

board = daq2(platform="zcu102")
board.output_filename = "fmcdaq2.dts"
board.gen_dt_from_config(solver_config)
```

### List Kuiper-supported boards

```bash
adidtc kuiper-boards
```

### Inspect device trees on live hardware

```bash
adidtc -c remote_sysfs -i 192.168.2.1 prop -cp adi,ad9361 clock-output-names
```

![props command](doc/source/_static/media/props.gif)

## Supported Hardware

| Converter Family | Platforms | HW Validated |
|---|---|---|
| AD9081 / AD9082 / AD9083 (MxFE) | ZCU102, ZC706, VPK180 | ZCU102 ✓ |
| AD9084 | VCU118, VPK180 | |
| ADRV9009 / ADRV9025 / ADRV9008 | ZCU102, ZC706, Arria10, ZU11EG | ZCU102 ✓ |
| ADRV9009-ZU11EG (SOM) | ADRV2CRR-FMC carrier | |
| AD936x / FMComms2-5 (SDR) | Zedboard, ZC702, ZC706, ZCU102 | |
| ADRV9361-Z7035 / ADRV9364-Z7020 (SOM) | BOB, FMC carriers | |
| FMCDAQ2 (AD9680 + AD9144) | ZCU102, ZC706, Arria10 | ZCU102 ✓ |
| FMCDAQ3 (AD9680 + AD9152) | ZCU102, ZC706 | ZCU102 ✓ |
| Precision ADCs / Sensors | Zedboard, Raspberry Pi | |

## Documentation

- [Quick Start](https://analogdevicesinc.github.io/pyadi-dt/quickstart.html)
- [Device Tree Generation (non-XSA)](https://analogdevicesinc.github.io/pyadi-dt/board_class_workflow.html)
- [XSA Pipeline Guide](https://analogdevicesinc.github.io/pyadi-dt/xsa.html)
- [BoardModel API Reference](https://analogdevicesinc.github.io/pyadi-dt/api/model.html)
- [Creating Templates from Bindings](https://analogdevicesinc.github.io/pyadi-dt/creating_templates.html)
- [Visualization & Diagnostics](https://analogdevicesinc.github.io/pyadi-dt/visualization.html)
- [Developer Guide](https://analogdevicesinc.github.io/pyadi-dt/xsa_developer.html)

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -vs

# Type check
nox -s ty

# Build docs
nox -s docs
```

## License

[Eclipse Public License 2.0](LICENSE)
