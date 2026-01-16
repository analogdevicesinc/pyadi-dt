# AD9081 Device Tree Generation

This guide covers device tree source (DTS) file generation for AD9081 FMC evaluation boards across multiple FPGA platforms.

## Overview

The `adidtc gen-dts` command generates platform-specific device tree source files for AD9081-based systems from JSON configuration files. These DTS files can be compiled to DTB format and deployed to target hardware.

### Supported Platforms

| Platform | SoC/FPGA | Architecture | JESD PHY | Max Lane Rate |
|----------|----------|--------------|----------|---------------|
| ZCU102 | Zynq UltraScale+ | ARM64 | GTH | 16.3 Gbps |
| VPK180 | Versal | ARM64 | GTY | 28.21 Gbps |
| ZC706 | Zynq-7000 | ARM | GTX | 12.5 Gbps |

## Quick Start

### 1. Install pyadi-dt

```bash
pip install -e .
```

### 2. Prepare Linux Kernel Source

The tool requires Linux kernel source containing base device tree files. Choose one method:

**Option A: Clone to default location**
```bash
git clone https://github.com/analogdevicesinc/linux.git
```

**Option B: Set environment variable**
```bash
export LINUX_KERNEL_PATH=/path/to/your/linux
```

**Option C: Pass via command line**
```bash
adidtc gen-dts -p zcu102 -c config.json -k /path/to/linux
```

### 3. Create Configuration File

Create a JSON file with your system configuration (see [Configuration File Format](#configuration-file-format)).

### 4. Generate Device Tree

```bash
adidtc gen-dts --platform zcu102 --config my_config.json
```

Output: `generated_dts/ad9081_fmc_zcu102.dts`

### 5. Compile to DTB (Optional)

```bash
adidtc gen-dts --platform zcu102 --config my_config.json --compile
```

Output: `generated_dts/ad9081_fmc_zcu102.dtb`

## Command Line Interface

### gen-dts Command

```bash
adidtc gen-dts [OPTIONS]
```

**Required Options:**
- `-p, --platform` : Target platform (`zcu102`, `vpk180`, or `zc706`)
- `-c, --config` : Path to JSON configuration file

**Optional:**
- `-k, --kernel-path` : Path to Linux kernel source (overrides env var)
- `-o, --output` : Custom output DTS file path
- `--compile` : Compile DTS to DTB after generation

### Examples

**Basic generation:**
```bash
adidtc gen-dts -p zcu102 -c configs/default.json
```

**With custom kernel path:**
```bash
adidtc gen-dts -p vpk180 -c configs/vpk180.json -k ~/linux-adi
```

**Generate and compile:**
```bash
adidtc gen-dts -p zc706 -c configs/zc706.json --compile
```

**Custom output location:**
```bash
adidtc gen-dts -p zcu102 -c cfg.json -o /tmp/custom.dts
```

(configuration-file-format)=
## Configuration File Format

Configuration files are JSON documents containing clock, JESD, and datapath settings. These are typically generated from [pyadi-jif](https://github.com/analogdevicesinc/pyadi-jif).

### Complete Example

```json
{
  "converter": {
    "type": "ad9081"
  },
  "clock": {
    "vcxo": 100000000,
    "vco": 3000000000,
    "output_clocks": {
      "AD9081_ref_clk": {"divider": 6},
      "adc_sysref": {"divider": 256},
      "dac_sysref": {"divider": 256},
      "adc_fpga_ref_clk": {"divider": 8},
      "adc_fpga_link_out_clk": {"divider": 8},
      "dac_fpga_ref_clk": {"divider": 8},
      "dac_fpga_link_out_clk": {"divider": 8}
    }
  },
  "fpga_adc": {
    "sys_clk_select": "XCVR_QPLL",
    "out_clk_select": "XCVR_REFCLK_DIV2"
  },
  "fpga_dac": {
    "sys_clk_select": "XCVR_QPLL",
    "out_clk_select": "XCVR_REFCLK_DIV2"
  },
  "jesd_adc": {
    "M": 8,
    "L": 4,
    "S": 1,
    "F": 2,
    "K": 32,
    "Np": 16,
    "CS": 0,
    "HD": 1,
    "jesd_mode": 9,
    "jesd_class": "jesd204b",
    "converter_clock": 4000000000,
    "sample_clock": 250000000
  },
  "jesd_dac": {
    "M": 8,
    "L": 4,
    "S": 1,
    "F": 4,
    "K": 32,
    "Np": 16,
    "CS": 0,
    "HD": 0,
    "jesd_mode": 10,
    "jesd_class": "jesd204b",
    "converter_clock": 12000000000,
    "sample_clock": 500000000
  },
  "datapath_adc": {
    "cddc": {
      "enabled": [true, true, true, true],
      "decimations": [4, 4, 4, 4],
      "nco_frequencies": [0, 0, 0, 0]
    },
    "fddc": {
      "enabled": [true, true, true, true, true, true, true, true],
      "decimations": [1, 1, 1, 1, 1, 1, 1, 1],
      "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0]
    }
  },
  "datapath_dac": {
    "cduc": {
      "enabled": [true, true, true, true],
      "interpolation": 6,
      "sources": [[0, 1], [2, 3], [4, 5], [6, 7]],
      "nco_frequencies": [0, 0, 0, 0]
    },
    "fduc": {
      "enabled": [true, true, true, true, true, true, true, true],
      "interpolation": 4,
      "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0]
    }
  }
}
```

### Configuration Sections

#### Clock Configuration

**HMC7044 Clock Chip Settings:**
- `vcxo`: Reference oscillator frequency (100 MHz or 122.88 MHz typical)
- `vco`: PLL2 VCO frequency (up to 3 GHz)
- `output_clocks`: Clock output dividers for each channel

#### FPGA Configuration

**Transceiver Settings (Optional):**

If omitted, platform defaults are used:

| Platform | Default ADC PLL | Default DAC PLL |
|----------|-----------------|-----------------|
| ZCU102 | XCVR_QPLL | XCVR_QPLL |
| VPK180 | XCVR_QPLL0 | XCVR_QPLL0 |
| ZC706 | XCVR_QPLL | XCVR_QPLL |

**Available PLL Options:**
- ZCU102/ZC706: `XCVR_QPLL`, `XCVR_CPLL`
- VPK180: `XCVR_QPLL0`, `XCVR_QPLL1`, `XCVR_CPLL`

**Clock Selection Options:**
- `XCVR_REFCLK`: Reference clock
- `XCVR_REFCLK_DIV2`: Reference clock divided by 2

#### JESD Configuration

**ADC/DAC Link Parameters:**
- `M`: Converters per link
- `L`: Lanes per link
- `S`: Samples per converter per frame
- `F`: Octets per frame
- `K`: Frames per multiframe
- `Np`: Converter resolution (bits)
- `CS`: Control bits per sample
- `HD`: High density mode (0 or 1)
- `jesd_mode`: Quick config mode (see AD9081 datasheet)
- `jesd_class`: JESD204 subclass (`jesd204a`, `jesd204b`, `jesd204c`)
- `converter_clock`: Converter sampling clock (Hz)
- `sample_clock`: Output sample rate (Hz)

#### Datapath Configuration

**ADC Datapath:**
- `cddc`: Coarse DDC settings (4 channels)
  - `enabled`: Enable/disable each CDDC
  - `decimations`: Decimation factor per CDDC
  - `nco_frequencies`: NCO frequency shift (Hz)
- `fddc`: Fine DDC settings (8 channels)
  - Similar structure to CDDC

**DAC Datapath:**
- `cduc`: Coarse DUC settings (4 channels)
  - `enabled`: Enable/disable each CDUC
  - `interpolation`: Interpolation factor
  - `sources`: FDUC channel mapping for each CDUC
  - `nco_frequencies`: NCO frequency shift (Hz)
- `fduc`: Fine DUC settings (8 channels)
  - `enabled`: Enable/disable each FDUC
  - `interpolation`: Interpolation factor
  - `nco_frequencies`: NCO frequency shift (Hz)

## Python API Usage

### Basic Usage

```python
from adidt.boards.ad9081_fmc import ad9081_fmc
import json

# Load configuration
with open('config.json', 'r') as f:
    cfg = json.load(f)

# Initialize board for target platform
board = ad9081_fmc(platform='zcu102', kernel_path='/path/to/linux')

# Validate and apply defaults
cfg = board.validate_and_default_fpga_config(cfg)

# Map configuration to board layout
clock, adc, dac, fpga = board.map_clocks_to_board_layout(cfg)

# Generate DTS
output_file = board.gen_dt(
    clock=clock,
    adc=adc,
    dac=dac,
    fpga=fpga,
    config_source='config.json'
)

print(f"Generated: {output_file}")
```

### Advanced Usage

```python
# Custom output location
board.output_filename = '/custom/path/output.dts'

# Get DTC include paths for manual compilation
include_paths = board.get_dtc_include_paths()

# Access platform configuration
print(f"Platform: {board.platform}")
print(f"Architecture: {board.platform_config['arch']}")
print(f"JESD PHY: {board.platform_config['jesd_phy']}")
```

## Kernel Source Configuration

The tool needs Linux kernel source to include base platform DTS files. Three-tier priority system:

1. **CLI argument** (highest): `--kernel-path /path/to/linux`
2. **Environment variable**: `export LINUX_KERNEL_PATH=/path/to/linux`
3. **Default location** (lowest): `./linux` in project root

### Recommended Kernel Sources

**ADI Linux Fork (Recommended):**
```bash
git clone https://github.com/analogdevicesinc/linux.git
cd linux
git checkout adi-{version}
```

**Xilinx Linux Fork:**
```bash
git clone https://github.com/Xilinx/linux-xlnx.git
cd linux-xlnx
git checkout xlnx_rebase_v{version}
```

### Required Files

The tool validates these files exist:

| Platform | Required DTS File |
|----------|-------------------|
| ZCU102 | `arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev1.0.dts` |
| VPK180 | `arch/arm64/boot/dts/xilinx/versal-vpk180-revA.dts` |
| ZC706 | `arch/arm/boot/dts/xilinx/zynq-zc706.dts` |

## Compilation

### Manual Compilation

```bash
# Set kernel path
KERNEL=/path/to/linux

# ZCU102 (ARM64)
dtc -I dts -O dtb \
  -i $KERNEL/arch/arm64/boot/dts \
  -i $KERNEL/arch/arm64/boot/dts/xilinx \
  -i $KERNEL/include \
  -o output.dtb input.dts

# ZC706 (ARM)
dtc -I dts -O dtb \
  -i $KERNEL/arch/arm/boot/dts \
  -i $KERNEL/arch/arm/boot/dts/xilinx \
  -i $KERNEL/include \
  -o output.dtb input.dts
```

### Automated Compilation

```bash
adidtc gen-dts -p zcu102 -c config.json --compile
```

The tool automatically:
1. Generates DTS file
2. Determines correct include paths
3. Invokes `dtc` compiler
4. Produces DTB file alongside DTS

### DTC Requirements

- **Version**: >= 1.4.6 recommended
- **Installation**:
  ```bash
  # Ubuntu/Debian
  sudo apt-get install device-tree-compiler
  
  # Fedora/RHEL
  sudo dnf install dtc
  
  # Build from source
  git clone https://git.kernel.org/pub/scm/utils/dtc/dtc.git
  cd dtc
  make && sudo make install
  ```

## Troubleshooting

### Kernel Path Not Found

**Error:**
```
FileNotFoundError: Kernel source path not found: ./linux
```

**Solutions:**
1. Clone kernel to `./linux`: `git clone https://github.com/analogdevicesinc/linux.git`
2. Set environment: `export LINUX_KERNEL_PATH=/your/kernel/path`
3. Use CLI argument: `--kernel-path /your/kernel/path`

### Base DTS File Missing

**Error:**
```
FileNotFoundError: Base DTS file not found: arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10.dts
```

**Solutions:**
1. Ensure you're using a compatible kernel branch (ADI or Xilinx fork)
2. Check kernel version supports your platform
3. Verify file path in kernel source tree

### DTC Compilation Failed

**Error:**
```
Error: <input>:10.1-5 syntax error
```

**Solutions:**
1. Check DTS syntax in generated file
2. Verify all #include files are accessible
3. Update dtc to latest version
4. Review kernel source compatibility

### Platform Not Supported

**Error:**
```
ValueError: Platform 'vcu118' not supported
```

**Solution:**
Currently supported platforms are `zcu102`, `vpk180`, and `zc706`. Other platforms can be added by:
1. Adding platform config to `ad9081_fmc.PLATFORM_CONFIGS`
2. Creating platform-specific template
3. Verifying base DTS file availability

## Adding New Platforms

To add support for a new FPGA platform:

### 1. Add Platform Configuration

Edit `adidt/boards/ad9081_fmc.py`:

```python
PLATFORM_CONFIGS = {
    'new_platform': {
        'template_filename': 'ad9081_fmc_new_platform.tmpl',
        'base_dts_file': 'arch/arm64/boot/dts/vendor/board.dts',
        'base_dts_include': 'board.dts',
        'arch': 'arm64',
        'jesd_phy': 'GTH',
        'default_fpga_adc_pll': 'XCVR_QPLL',
        'default_fpga_dac_pll': 'XCVR_QPLL',
        'spi_bus': 'spi1',
        'output_dir': 'generated_dts',
    },
}
```

### 2. Create Template

Create `adidt/templates/ad9081_fmc_new_platform.tmpl` based on existing templates.

Key sections to customize:
- Clock references (`&clk_name`)
- SPI bus reference (`&spi0` or `&spi1`)
- JESD core clock names
- GPIO references

### 3. Add Tests

Add test configuration in `test/ad9081/configs/new_platform_config.json`.

Update `test/ad9081/test_ad9081_gen.py` to include new platform in parametrized tests.

### 4. Update Documentation

Add platform to supported platforms table and any platform-specific notes.

## Reference

### Configuration Templates

Example configurations are provided in `test/ad9081/configs/`:
- `zcu102_config.json`: ZCU102 reference design
- `vpk180_config.json`: VPK180 reference design  
- `zc706_config.json`: ZC706 reference design

### Related Resources

- [AD9081 Product Page](https://www.analog.com/ad9081)
- [AD9081 Linux Driver](https://wiki.analog.com/resources/tools-software/linux-drivers/iio-mxfe/ad9081)
- [AD9081 FMC-EBZ User Guide](https://wiki.analog.com/resources/eval/user-guides/quadmxfe)
- [JESD204B/C Overview](https://www.analog.com/en/technical-articles/jesd204b-survival-guide.html)
- [Linux Device Tree Documentation](https://www.kernel.org/doc/Documentation/devicetree/)

### Support

For issues or questions:
- GitHub Issues: https://github.com/analogdevicesinc/pyadi-dt/issues
- EngineerZone: https://ez.analog.com/

---

**Last Updated:** 2026-01-14  
**Version:** 1.0
