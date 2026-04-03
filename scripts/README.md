# Scripts

This directory contains utility scripts for managing the pyadi-dt project.

## generate_reference_targets.py

Automatically generates `adidt/templates/reference_dts_targets.json` by analyzing reference DTS files from the Linux kernel repository.

### Features

- **Auto-discovery**: Automatically finds all relevant ADI board DTS files in the Linux kernel tree
- **Smart analysis**: Extracts board type, platform, architecture, SoC type, transceivers, clock chips, and more
- **Template detection**: Automatically finds corresponding pyadi-dt template files
- **Variant discovery**: Identifies related DTS variants for each board/platform combination

### Usage

#### Auto-discover all reference DTS files

```bash
python scripts/generate_reference_targets.py --linux-path ./linux
```

This will:
1. Search the Linux kernel tree for all ADI board DTS files
2. Analyze each file to extract configuration
3. Generate `adidt/templates/reference_dts_targets.json`

#### Add specific target files

```bash
python scripts/generate_reference_targets.py --linux-path ./linux \
  --target arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-ad9081.dts \
  --target arch/arm64/boot/dts/xilinx/versal-vpk180-reva-ad9081.dts \
  --target arch/arm/boot/dts/xilinx/zynq-zc706-adv7511-ad9081.dts
```

#### Custom output location

```bash
python scripts/generate_reference_targets.py --linux-path ./linux \
  --output custom_targets.json
```

#### Merge with existing file

Use the `--merge` flag to append/merge new boards or platforms into an existing JSON file instead of overwriting it:

```bash
# Add a new platform to existing file
python scripts/generate_reference_targets.py --linux-path ./linux --merge \
  --target arch/arm64/boot/dts/xilinx/versal-vck190-reva-ad9081.dts
```

This will:
- Preserve all existing boards and platforms not in the new data
- Add new boards if they don't exist
- Add new platforms to existing boards
- Update existing platforms with new data
- Merge additional_variants (keeps unique entries)
- Display what was added or updated

Example output:
```
Analyzing 1 specified DTS files...
Merging with existing file: adidt/templates/reference_dts_targets.json
  + Added new platform: ad9081/vck190
Updated adidt/templates/reference_dts_targets.json (merged with existing data)
```

**Use cases for merge:**
- Adding support for a new platform variant without regenerating everything
- Incrementally building up the targets file
- Updating specific board configurations while preserving others
- Adding newly discovered DTS files from kernel updates

### What the script analyzes

For each DTS file, the script extracts:

- **Board type**: ad9081, ad9084, adrv9009, daq2
- **Platform**: zcu102, vpk180, vck190, zc706
- **Architecture**: arm, arm64
- **SoC type**: Zynq-7000, Zynq UltraScale+, Versal Premium, etc.
- **Transceivers**: GTH, GTY, GTX
- **Base includes**: Platform DTSI files that must be included
- **Clock reference**: zynqmp_clk, versal_clk, clkc
- **SPI bus**: spi0, spi1
- **Default PLL**: XCVR_QPLL, XCVR_CPLL, etc.
- **Clock chips**: HMC7044, AD9528, ADF4382, etc.
- **Template file**: Corresponding pyadi-dt template (if exists)
- **Variants**: Related DTS configurations for the same board/platform

### When to use

Run this script when:

1. **Adding new board support**: After adding reference DTS files to the Linux kernel
2. **Updating Linux kernel**: After syncing to a newer kernel version with new/changed DTS files
3. **Documenting existing boards**: To generate up-to-date documentation of supported configurations

### Example workflow for adding a new board

```bash
# 1. Add reference DTS file to Linux kernel (or sync kernel repo)
cd linux
git pull

# 2. Generate updated reference targets
cd ..
python scripts/generate_reference_targets.py --linux-path ./linux

# 3. Review the generated JSON
cat adidt/templates/reference_dts_targets.json

# 4. Create corresponding pyadi-dt template based on the reference
# (The script will detect it on the next run)
```

### Output format

The script generates a JSON file with this structure:

```json
{
  "boards": {
    "ad9081": {
      "description": "AD9081/MxFE FMC Evaluation Board",
      "platforms": {
        "zcu102": {
          "architecture": "arm64",
          "soc": "Zynq UltraScale+ MPSoC",
          "transceivers": "GTH",
          "reference_dts": "arch/arm64/boot/dts/xilinx/...",
          "base_includes": ["zynqmp-zcu102-rev1.0.dts"],
          "template": "ad9081_fmc_zcu102.tmpl",
          "clock_reference": "zynqmp_clk",
          "spi_bus": "spi1",
          "default_pll": "XCVR_QPLL",
          "additional_variants": [...]
        }
      },
      "clock_chips": ["hmc7044"],
      "shared_dtsi": []
    }
  },
  "base_platform_files": {...},
  "transceiver_types": {...}
}
```

### Requirements

- Python 3.10+
- Access to Linux kernel source tree with ADI board DTS files

### Troubleshooting

**"Linux path does not exist"**
- Verify the path to your Linux kernel source tree is correct
- Ensure you've cloned/synced the kernel repository

**"Could not identify board/platform"**
- The DTS filename doesn't match expected patterns
- Add custom detection patterns to `BOARD_PATTERNS` or `PLATFORM_PATTERNS` in the script

**"Template not found"**
- This is expected if the pyadi-dt template hasn't been created yet
- The `template` field will be `null` in the JSON
- Create the template file and re-run the script to update

**No files discovered**
- Verify the Linux kernel tree contains ADI board DTS files
- Check the search paths in `discover_reference_dts_files()` function

---

## ADI Binding Collection and Audit

The scripts in this directory include a small pair for Linux devicetree binding
inventory and support discovery:

- `collect_adi_bindings.py`: parse ADI binding files from a Linux checkout and
  emit a compact JSON/Markdown summary.
- `audit_adi_bindings.py`: compare parsed compatibles against known pyadi-dt
  compatibles and identify undocumented entries.

### Usage

Collect all ADI bindings from a local Linux tree:

```bash
python scripts/collect_adi_bindings.py --linux-path ./linux --output adi_bindings.json
```

Collect Markdown report and skip TXT parsing:

```bash
python scripts/collect_adi_bindings.py \
  --linux-path ./linux \
  --no-include-txt \
  --report adi_bindings_report.md
```

Audit against project support:

```bash
python scripts/audit_adi_bindings.py \
  --linux-path ./linux \
  --project-root . \
  --output adi_undocumented.json \
  --fail-on-undocumented
```

Generate starter board templates plus Markdown documentation for undocumented bindings:

```bash
python scripts/audit_adi_bindings.py \
  --linux-path ./linux \
  --project-root . \
  --generate-templates \
  --template-json-out generated_templates.json \
  --template-doc-out adidt/templates/boards/README.generated.md
```

This generation flow:

- Maps undocumented compatibles to known board names using `adidt/templates/reference_dts_targets.json`
- Creates starter `.tmpl` files under `adidt/templates/boards`
- Skips existing templates unless `--force` is set
- Emits Markdown grouped into generated, skipped, and not-generated entries

The collection script supports the same template-generation flags when you want
the raw binding inventory and starter template artifacts in one run.

If `--linux-path` is unavailable, both scripts can clone from a remote URL:

```bash
python scripts/collect_adi_bindings.py \
  --linux-url https://github.com/analogdevicesinc/linux.git \
  --linux-ref v6.16
```

## Developer Guide

This section explains how the JSON generation works internally, useful for maintaining and extending the script.

### Architecture Overview

The script consists of three main components:

1. **DTSAnalyzer class**: Core analysis engine that parses DTS files and extracts metadata
2. **Discovery functions**: Find relevant DTS files in the kernel tree
3. **Merge logic**: Intelligently combines new and existing data

```
Linux Kernel Tree
       ↓
   Discovery
       ↓
  DTS Files List
       ↓
   DTSAnalyzer
       ↓
  Metadata Extraction
       ↓
   JSON Structure
       ↓
  Merge (optional)
       ↓
 Output JSON File
```

### How DTS Analysis Works

The analysis pipeline for each DTS file:

#### 1. File Identification

The script uses regex patterns to identify board and platform from the DTS filename:

```python
# Board patterns
BOARD_PATTERNS = {
    r'ad9081': 'ad9081',
    r'ad9084': 'ad9084',
    r'adrv9009': 'adrv9009',
    r'fmcdaq2': 'daq2',
}

# Platform patterns
PLATFORM_PATTERNS = {
    r'zcu102': 'zcu102',
    r'vpk180': 'vpk180',
    r'vck190': 'vck190',
    r'zc706': 'zc706',
}
```

**Example**: `zynqmp-zcu102-rev10-ad9081.dts`
- Board: `ad9081` (matches pattern)
- Platform: `zcu102` (matches pattern)

#### 2. Content Analysis

The script reads the DTS file and analyzes its content:

**Architecture detection**:
```python
if '/arm64/' in dts_path:
    architecture = 'arm64'
elif '/arm/' in dts_path:
    architecture = 'arm'
```

**SoC type detection**:
- Searches for `compatible` strings: `xlnx,zynqmp`, `xlnx,versal`, etc.
- Maps to human-readable names: "Zynq UltraScale+ MPSoC", "Versal Premium"

**Transceiver type detection**:
- ARM64 ZCU102 → GTH (Gigabit Transceiver High-performance)
- Versal (VPK180, VCK190) → GTY (up to 32.75 Gbps)
- ARM ZC706 → GTX (up to 12.5 Gbps)

#### 3. Include File Parsing

Extracts base platform DTSI files that must be included:

```python
include_pattern = r'#include\s+"([^"]+)"'
includes = re.findall(include_pattern, content)
```

Filters out ADI-specific includes to keep only platform base files:
- ✓ `zynqmp-zcu102-rev1.0.dts`
- ✓ `versal-vpk180-revA.dts`
- ✗ `adi-ad9081.dtsi` (board-specific, excluded)

#### 4. Hardware Configuration Detection

**Clock reference**:
```python
if 'zynqmp_clk' in content:
    clock_ref = 'zynqmp_clk'  # ZynqMP devices
elif 'versal_clk' in content:
    clock_ref = 'versal_clk'  # Versal devices
elif 'clkc' in content:
    clock_ref = 'clkc'        # Zynq-7000 devices
```

**SPI bus**:
```python
if '&spi1' in content:
    spi_bus = 'spi1'
elif '&spi0' in content:
    spi_bus = 'spi0'
```

**PLL configuration**:
- Most boards: Single PLL string (e.g., `XCVR_QPLL`)
- ADRV9009: Dictionary with separate RX/TX/ORX PLLs
  ```python
  {
      'rx': 'XCVR_CPLL',
      'tx': 'XCVR_QPLL',
      'orx': 'XCVR_CPLL'
  }
  ```

**Clock chips**:
Searches for compatible strings in DTS content:
```python
clock_chips = []
if 'adi,hmc7044' in content:
    clock_chips.append('hmc7044')
if 'adi,ad9528' in content:
    clock_chips.append('ad9528')
if 'adi,adf4382' in content:
    clock_chips.append('adf4382')
```

#### 5. Template Detection

Attempts to find corresponding pyadi-dt template files:

```python
patterns = [
    f"{board}_fmc_{platform}.tmpl",  # ad9081_fmc_zcu102.tmpl
    f"{board}_{platform}.tmpl",       # daq2_zcu102.tmpl
    f"{board}.tmpl",                   # daq2.tmpl (generic)
]
```

Checks if template exists in `adidt/templates/` directory.

#### 6. Variant Discovery

Finds related DTS files for the same board/platform:

```python
# For zynqmp-zcu102-rev10-ad9081.dts, finds:
# - zynqmp-zcu102-rev10-ad9081-m8-l4.dts
# - zynqmp-zcu102-rev10-ad9081-204c-txmode0-rxmode1.dts
# - etc.
```

**Variant pattern**: `{base_name}-*.dts` where base_name excludes revision numbers.

Limits to 6 variants to keep JSON manageable.

### Data Structures

#### PlatformConfig (per platform)

```python
@dataclass
class PlatformConfig:
    architecture: str           # "arm" or "arm64"
    soc: str                    # "Zynq UltraScale+ MPSoC"
    transceivers: str           # "GTH", "GTY", "GTX"
    reference_dts: str          # Path relative to linux root
    base_includes: List[str]    # Platform DTSI files
    template: Optional[str]     # Template filename or None
    clock_reference: str        # Clock node reference
    spi_bus: str               # "spi0" or "spi1"
    default_pll: str | Dict    # PLL configuration
    additional_variants: List[str]  # Related DTS files
```

#### BoardConfig (per board)

```python
@dataclass
class BoardConfig:
    description: str            # Human-readable name
    platforms: Dict[str, PlatformConfig]
    clock_chips: List[str]      # Clock ICs on board
    shared_dtsi: List[str]      # Shared DTSI files
    components: Optional[Dict]  # ADC/DAC info (daq2 only)
```

#### Output JSON Structure

```json
{
  "$schema": "...",
  "description": "...",
  "version": "1.0.0",
  "boards": {
    "<board_name>": {
      "description": "...",
      "platforms": {
        "<platform_name>": { PlatformConfig },
        ...
      },
      "clock_chips": [...],
      "shared_dtsi": [...],
      "components": {...}  // optional
    },
    ...
  },
  "base_platform_files": {
    "arm64": { "<platform>": {...}, ... },
    "arm": { "<platform>": {...}, ... }
  },
  "transceiver_types": {
    "GTH": {...},
    "GTY": {...},
    "GTX": {...}
  }
}
```

### Merge Algorithm

When `--merge` flag is used, the script performs intelligent merging:

```python
def _merge_json_data(existing, new):
    # 1. Start with existing data
    merged = existing.copy()

    # 2. For each board in new data:
    for board_name, new_board in new['boards'].items():
        if board_name not in merged['boards']:
            # New board → add entirely
            merged['boards'][board_name] = new_board
        else:
            # Existing board → merge platforms
            existing_board = merged['boards'][board_name]

            # 3. Merge board-level arrays (clock_chips, shared_dtsi)
            #    using set union to keep unique

            # 4. For each platform in new board:
            for platform_name, new_platform in new_board['platforms'].items():
                if platform_name not in existing_board['platforms']:
                    # New platform → add to board
                    existing_board['platforms'][platform_name] = new_platform
                else:
                    # Existing platform → update all fields
                    # Merge additional_variants (keep unique)
                    existing_platform = existing_board['platforms'][platform_name]
                    existing_platform.update(new_platform)

    return merged
```

**Key behaviors**:
- **Additive**: Never removes existing boards or platforms
- **Update**: Overwrites platform fields with new values
- **Set union**: Merges variant lists (unique entries only)
- **Feedback**: Console output shows additions (+) and updates (↻)

### Extending for New Boards

To add support for a new board type:

#### 1. Add board pattern

```python
# In identify_board() method
board_patterns = {
    'ad9081': 'ad9081',
    'ad9084': 'ad9084',
    'adrv9009': 'adrv9009',
    'daq2': 'daq2',
    'your_new_board': 'your_new_board',  # ADD THIS
}
```

#### 2. Add discovery pattern

```python
# In discover_reference_dts_files() function
search_patterns = [
    'arch/arm64/boot/dts/xilinx/*-ad9081.dts',
    'arch/arm64/boot/dts/xilinx/*-your_new_board.dts',  # ADD THIS
    # ...
]
```

#### 3. Add board description

```python
# In _get_board_description() method
descriptions = {
    'ad9081': 'AD9081/MxFE FMC Evaluation Board',
    'your_new_board': 'Your New Board Description',  # ADD THIS
}
```

#### 4. Add clock chip detection (if needed)

```python
# In identify_clock_chips() method
if 'adi,your-clock-chip' in dts_content:
    chips.append('your_clock_chip')
```

#### 5. Test

```bash
# Run with specific target
python scripts/generate_reference_targets.py --linux-path ./linux \
  --target arch/arm64/boot/dts/xilinx/platform-your_new_board.dts \
  --output /tmp/test.json

# Verify output
cat /tmp/test.json
```

### Extending for New Platforms

To add support for a new platform:

#### 1. Add platform pattern

```python
# In identify_platform() method
platform_patterns = {
    'zcu102': 'zcu102',
    'vpk180': 'vpk180',
    'your_platform': 'your_platform',  # ADD THIS
}
```

#### 2. Add transceiver mapping

```python
# In identify_transceivers() method
if platform == 'your_platform':
    if arch == 'arm64':
        return 'GTY'  # Or GTH, depending on platform
```

#### 3. Add base platform files

```python
# In _get_base_platform_files() method
'arm64': {
    'zcu102': {...},
    'your_platform': {  # ADD THIS
        'path': 'arch/arm64/boot/dts/xilinx/your-platform.dts',
        'includes': ['your-platform.dtsi', 'zynqmp.dtsi']
    },
}
```

#### 4. Add transceiver info (if new type)

```python
# In _get_transceiver_types() method
'transceiver_types': {
    'GTH': {...},
    'YOUR_NEW_TYPE': {  # ADD THIS IF NEEDED
        'description': 'Description',
        'platforms': ['your_platform'],
        'max_rate_gbps': 25.0
    }
}
```

### Pattern Matching Reference

#### Filename Patterns

The script expects DTS filenames following these conventions:

**Format**: `<soc>-<platform>-<rev>-<board>[<variant>].dts`

Examples:
- `zynqmp-zcu102-rev10-ad9081.dts` → board=ad9081, platform=zcu102
- `versal-vpk180-reva-ad9084.dts` → board=ad9084, platform=vpk180
- `zynq-zc706-adv7511-adrv9009.dts` → board=adrv9009, platform=zc706

**Variants** (optional suffix):
- `-m8-l4`: Mode 8, Lane 4 configuration
- `-204c-txmode0-rxmode1`: JESD204C specific modes
- `-jesd204-fsm`: JESD204 FSM variant

#### Content Patterns

Searches for these strings in DTS content:

**Compatible strings**:
- `"xlnx,zynqmp"` → Zynq UltraScale+ MPSoC
- `"xlnx,versal"` → Versal ACAP
- `"xlnx,zynq-7000"` → Zynq-7000 SoC

**Node references**:
- `&spi0`, `&spi1` → SPI bus assignment
- `&zynqmp_clk`, `&versal_clk`, `&clkc` → Clock reference

**Clock chips**:
- `"adi,hmc7044"` → HMC7044 clock generator
- `"adi,ad9528"` → AD9528 clock generator
- `"adi,adf4382"` → ADF4382 frequency synthesizer

### Testing Changes

When modifying the script, test with:

```bash
# Test single file
python scripts/generate_reference_targets.py --linux-path ./linux \
  --target arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-ad9081.dts \
  --output /tmp/test_output.json

# Verify JSON structure
python -m json.tool /tmp/test_output.json > /dev/null && echo "Valid JSON"

# Test merge functionality
python scripts/generate_reference_targets.py --linux-path ./linux \
  --target arch/arm64/boot/dts/xilinx/versal-vpk180-reva-ad9081.dts \
  --output /tmp/test_output.json --merge

# Test full auto-discovery
python scripts/generate_reference_targets.py --linux-path ./linux \
  --output /tmp/test_full.json

# Compare with expected output
diff <(python -m json.tool /tmp/test_full.json) \
     <(python -m json.tool adidt/templates/reference_dts_targets.json)
```

### Debugging Tips

**Enable verbose output**:
```python
# Add print statements in analyze_dts_file()
print(f"Analyzing: {dts_path}")
print(f"  Board: {board}, Platform: {platform}")
print(f"  Architecture: {architecture}")
```

**Check pattern matching**:
```python
# Test regex patterns
import re
filename = "zynqmp-zcu102-rev10-ad9081.dts"
for pattern, board_name in BOARD_PATTERNS.items():
    if re.search(pattern, filename):
        print(f"Matched board: {board_name}")
```

**Validate JSON output**:
```bash
# Use jq for pretty-printing and validation
cat output.json | jq '.'

# Check specific board
cat output.json | jq '.boards.ad9081'

# List all platforms
cat output.json | jq '.boards | to_entries[] | "\(.key): \(.value.platforms | keys)"'
```

### Common Gotchas

1. **Case sensitivity**: DTS filenames are case-sensitive, patterns must match exactly
2. **Path separators**: Use forward slashes even on Windows (Path object handles this)
3. **Variant limits**: Script limits to 6 variants per platform to avoid bloat
4. **Template naming**: Must match `{board}_fmc_{platform}.tmpl` pattern
5. **Merge behavior**: Merge doesn't remove platforms, only adds/updates
6. **Include filtering**: Only platform includes are kept, board-specific ones filtered out

### Maintenance Checklist

When updating for new kernel versions:

- [ ] Clone/sync Linux kernel repository
- [ ] Run script with auto-discovery
- [ ] Review new boards/platforms detected
- [ ] Verify transceiver types are correct
- [ ] Check SPI bus assignments match hardware
- [ ] Validate clock chip detection
- [ ] Test merge functionality
- [ ] Update patterns if new naming conventions found
- [ ] Commit updated JSON file
- [ ] Update documentation if behavior changed
