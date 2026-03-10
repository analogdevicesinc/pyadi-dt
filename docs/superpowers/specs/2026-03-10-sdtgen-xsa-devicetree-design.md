# XSA-to-DeviceTree Pipeline Design

**Date:** 2026-03-10
**Status:** Draft
**Topic:** sdtgen-driven devicetree generation with ADI driver nodes, JESD204 FSM support, and HTML visualization

---

## Overview

Extend pyadi-dt-xsa-powers with a new `xsa2dt` pipeline that:

1. Invokes `sdtgen` (lopper-based) as a subprocess against a Vivado XSA file to produce a base SDT/DTS
2. Parses the XSA `.hwh` hardware handoff to detect ADI AXI IP instances (JESD204 RX/TX, clkgen, converters)
3. Builds ADI driver nodes and JESD204 FSM framework bindings from detected topology + pyadi-jif JSON config
4. Merges ADI nodes with the base DTS, producing both a `.dtso` overlay and a merged `.dts`
5. Generates a self-contained interactive HTML visualization report

The existing `gen-dts` / Jinja2 template flow is untouched. All JESD204 IP targets ADI's `axi_jesd204_rx`/`tx` IPs with the ADI JESD204 FSM framework drivers.

**Minimum Python version:** 3.10 (consistent with existing `pyproject.toml` baseline).

---

## Architecture

### Module Structure

```
adidt/
  xsa/
    __init__.py
    sdtgen.py       # Stage 1: subprocess wrapper for sdtgen/lopper
    topology.py     # Stage 2: XSA .hwh parser → detected ADI IPs
    node_builder.py # Stage 3: ADI driver nodes + JESD204 FSM bindings
    merger.py       # Stage 4: DTS overlay (.dtso) + merged (.dts) output
    visualizer.py   # Stage 5: self-contained HTML report generator
  templates/
    xsa/
      jesd204_fsm.tmpl
      axi_ad9081.tmpl
      axi_ad9084.tmpl
      axi_clkgen.tmpl
  cli/
    main.py         # + new `xsa2dt` subcommand registered on existing `cli` group
scripts/
  embed_d3.py       # Developer utility: downloads and inlines D3.js into
                    # adidt/xsa/d3_bundle.js (committed to repo)
test/
  xsa/
    fixtures/       # Captured .hwh files for unit tests (no Vivado required)
    test_sdtgen.py  # Stage 1 tests (subprocess mocking)
    test_topology.py
    test_node_builder.py
    test_merger.py
    test_visualizer.py
docs/
  superpowers/
    specs/          # This file
```

### CLI

The new command is registered as a subcommand on the existing `cli` Click group in `adidt/cli/main.py` (entry point `adidtc`):

```
adidtc xsa2dt \
  --xsa        design_1.xsa \
  --config     ad9081_cfg.json \
  --output     ./generated/
```

`--platform` is omitted — the converter type and platform are inferred from the XSA topology. The `--output` directory is created if it does not exist.

Output in `./generated/`:
```
base/                            # raw sdtgen output
<converter>_<platform>.dtso      # ADI-only overlay
<converter>_<platform>.dts       # merged complete DTS
<converter>_<platform>_report.html  # interactive HTML visualization
```

Output filenames are derived from the first detected converter IP type (`axi_ad9081` → `ad9081`) and the detected FPGA part string from the `.hwh` mapped to a short platform name (`xc7z045` → `zc706`, `xczu9eg` → `zcu102`, etc.). An `UNKNOWN` fallback is used if the part is unrecognized.

---

## Stage 1: sdtgen Subprocess Wrapper (`sdtgen.py`)

### sdtgen CLI

`sdtgen` is the Xilinx-maintained lopper-based tool. As of the 2023.x release the invocation is:

```
sdtgen -s <xsa_path> -d <output_dir>
```

> **Implementation note:** The exact flags must be verified against the installed version at first call. `SdtgenRunner` should run `sdtgen --help` on first use (cached per-process) to confirm the flag set matches. If the flags differ, raise `SdtgenError` with the help output so the discrepancy is visible.

The expected output filename is `system-top.dts`. If that file is absent after a successful (exit-0) run, scan `output_dir` for `*.dts` files and use the first match; if none, raise `SdtgenError("sdtgen produced no .dts output")`.

### Interface

```python
class SdtgenRunner:
    def run(self, xsa_path: Path, output_dir: Path, timeout: int = 120) -> Path:
        """Invoke sdtgen and return path to generated base DTS."""
```

### Subprocess policy

- Use `subprocess.run(..., capture_output=True, timeout=timeout, check=False)`.
- On `TimeoutExpired`: kill the process, raise `SdtgenError("sdtgen timed out after {timeout}s")`.
- On non-zero exit: raise `SdtgenError` with decoded stderr.
- On `FileNotFoundError` (binary missing): raise `SdtgenNotFoundError` with install instructions pointing to the lopper/sdtgen GitHub.
- `KeyboardInterrupt` propagates naturally (no suppression).

---

## Stage 2: XSA Topology Parser (`topology.py`)

XSA files are ZIP archives containing a `.hwh` (Hardware Handoff) XML file — Vivado's machine-readable hardware description. Parses the `.hwh` without invoking sdtgen.

### Data Model

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Jesd204Instance:
    name: str                   # IP instance name from Vivado
    base_addr: int              # from hwh MEMRANGE/@BASEVALUE
    num_lanes: int              # from IP parameter C_NUM_LANES
    irq: Optional[int]          # interrupt number if INTERRUPT port connected; None otherwise
    link_clk: str               # clock net name on ACLK port
    direction: str              # "rx" or "tx"

@dataclass
class ClkgenInstance:
    name: str
    base_addr: int
    output_clks: list[str] = field(default_factory=list)
    # output_clks[i] = clock net name for output index i (from CLK_OUT<i> port connections)

@dataclass
class ConverterInstance:
    name: str
    ip_type: str                # "axi_ad9081", "axi_ad9084", etc.
    base_addr: int
    spi_bus: Optional[int]      # AXI SPI controller index; None if not resolvable from .hwh
    spi_cs: Optional[int]       # chip-select index; None if not resolvable from .hwh

@dataclass
class XsaTopology:
    jesd204_rx: list[Jesd204Instance] = field(default_factory=list)
    jesd204_tx: list[Jesd204Instance] = field(default_factory=list)
    clkgens: list[ClkgenInstance] = field(default_factory=list)
    converters: list[ConverterInstance] = field(default_factory=list)
    fpga_part: str = ""         # e.g. "xczu9eg-ffvb1156-2-e"
```

### .hwh Parsing Strategy

The `.hwh` XML root is `<EDKPROJECT>`. Key paths:

- IP instances: `//MODULES/MODULE[@MODTYPE]` — `MODTYPE` is the IP type (e.g. `axi_jesd204_rx`)
- Base address: `MODULE/MEMRANGES/MEMRANGE[@INSTANCE]/@BASEVALUE` (hex string, strip `0x`)
- IP parameters: `MODULE/PARAMETERS/PARAMETER[@NAME=<name>]/@VALUE`
- Clock connections: `MODULE/PORTS/PORT[@DIR="I" and @SIGIS="CLK"]/@SIGNAME`
- Interrupt connections: `MODULE/PORTS/PORT[@NAME="interrupt"]/@SIGNAME` → trace net to AXI interrupt controller to determine IRQ number
- FPGA part: `//PROJECT/@DEVICE` + `/@PACKAGE` + `/@SPEEDGRADE`

**SPI resolution:** `spi_bus` and `spi_cs` are best-effort from `.hwh`. If the AXI Quad SPI master driving the converter's SPI port cannot be unambiguously traced, set both to `None` and emit a warning. The JSON config may supply these values as overrides via a `spi_bus`/`spi_cs` top-level key.

If no recognized ADI IPs are detected, emit a `UserWarning` and return an empty `XsaTopology` (pipeline continues, producing base DTS only).

---

## Stage 3: ADI Node Builder (`node_builder.py`)

Takes `XsaTopology` + pyadi-jif JSON config dict. Renders Jinja2 templates from `templates/xsa/`.

### Clock Resolution

The pyadi-jif JSON config contains a `clock` dict with output frequencies keyed by logical name (e.g. `"hmc7044_out_freq": {...}`). The `ClkgenInstance.output_clks` list contains `.hwh` clock net names (e.g. `clk_wiz_0/clk_out1`).

Resolution strategy:
1. Build a map `{net_name: clkgen_instance}` from all `ClkgenInstance.output_clks`.
2. For each JESD204 instance's `link_clk` net name, look up the driving `ClkgenInstance`.
3. Cross-reference against JSON `clock` entries by frequency match (within 1% tolerance) to assign the logical clock name and HMC7044 channel.
4. If no match: emit `UserWarning("unresolved clock net {name}")` and use the net name literally in the template.

This replaces the platform-specific `map_clocks_to_board_layout()` for the XSA flow.

### JESD204 FSM Node Template

Templates use Jinja2 `{{ variable }}` syntax. Base address rendered as `0x{{ "%08X" | format(base_addr) }}`. Example rendered output:

```dts
axi_ad9081_rx_jesd: axi-jesd204-rx@44a90000 {
    compatible = "adi,axi-jesd204-rx-1.0";
    reg = <0x0 0x44a90000 0x0 0x1000>;
    interrupts = <0 54 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&axi_clkgen 0>, <&hmc7044 10>, <&axi_clkgen 1>;
    clock-names = "s_axi_aclk", "device_clk", "lane_clk";

    adi,octets-per-frame = <{{ F }}>;
    adi,frames-per-multiframe = <{{ K }}>;
};
```

All integer DTS properties rendered as decimal. `IRQ_TYPE_LEVEL_HIGH` is the literal string (macro, resolved by the kernel build).

### Conflict-free node names

Node labels derived from the `.hwh` instance name with non-alphanumeric characters replaced by `_`.

---

## Stage 4: DTS Merger (`merger.py`)

### Overlay (`.dtso`)

ADI nodes wrapped in `&label { ... }` references. Label discovery regex applied to base DTS:

```python
LABEL_RE = re.compile(r'^\s*(\w+)\s*:\s*\w+', re.MULTILINE)
```

Matches `label: node_type` patterns at any indentation. `#include`d files from the sdtgen output are followed (one level deep) for label scanning. Duplicate label names: first occurrence wins; a warning is emitted on duplicates.

### Merged (`.dts`)

ADI nodes inserted as children of the `amba` or `axi` bus node (the first node whose label matches `amba` or `axi`). If neither is found, nodes are appended at root level with a warning.

**Conflict resolution:** If the base DTS already contains a node at the same `reg` address as an ADI-generated node, the base node is replaced entirely and a `UserWarning` is emitted naming the replaced node. No silent merging of properties — the ADI node is authoritative.

### DTB compilation

If `dtc` is on PATH: `dtc -I dts -O dtb -o <output>.dtb <merged>.dts`. Skips with an info log if `dtc` is absent.

---

## Stage 5: HTML Visualizer (`visualizer.py`)

Self-contained `.html` with all JS/CSS inlined. Three panels:

1. **Node tree** — collapsible DTS node hierarchy with inline property search. ADI-injected nodes highlighted in a distinct color (e.g. amber border).
2. **Clock topology** — SVG diagram: VCXO → PLL → HMC7044 channels → converter clocks → JESD204 lane clocks. Values from pyadi-jif JSON.
3. **JESD204 data path** — SVG showing TX/RX lanes, framer/deframer instances, connection to converter IPs.

### D3.js bundling

`scripts/embed_d3.py` downloads D3.js (pinned version, e.g. v7.9.0) and writes it to `adidt/xsa/d3_bundle.js`. This file is **committed to the repository**. `visualizer.py` reads it at import time and inlines it into generated HTML.

CI lint check: verify `adidt/xsa/d3_bundle.js` exists and is non-empty. If absent, `visualizer.py` raises `RuntimeError("D3 bundle missing — run scripts/embed_d3.py")` at import time.

---

## Error Handling

| Stage | Failure | Behavior |
|-------|---------|----------|
| 1 | `sdtgen` not on PATH | `SdtgenNotFoundError` with install URL |
| 1 | sdtgen non-zero exit | `SdtgenError` with captured stderr |
| 1 | sdtgen timeout | `SdtgenError("timed out after Ns")`, process killed |
| 1 | No `.dts` in output dir | `SdtgenError("sdtgen produced no .dts output")` |
| 2 | No `.hwh` in XSA | `XsaParseError("no hardware handoff file found")` |
| 2 | No recognized ADI IPs | `UserWarning`, empty topology, base DTS only |
| 3 | JSON missing required keys | `ConfigError` naming the missing field |
| 3 | Clock ref unresolvable | `UserWarning` with net name, literal fallback |
| 3 | `spi_bus`/`spi_cs` not in `.hwh` | `None` on instance, `UserWarning` |
| 4 | `dtc` not found | Skip DTB, log info |
| 4 | Base node address conflict | Replace base node, `UserWarning` with node name |
| 5 | D3 bundle missing | `RuntimeError` at import |

---

## Testing

| Target | Approach |
|--------|----------|
| Stage 1 (`sdtgen.py`) | Unit tests mocking `subprocess.run`: verify correct args, stderr propagation, `SdtgenNotFoundError` on `FileNotFoundError`, timeout handling |
| Stage 2 (`topology.py`) | Unit tests with captured `.hwh` fixtures in `test/xsa/fixtures/` — one per converter type; no Vivado required |
| Stage 3 (`node_builder.py`) | Unit tests with topology fixtures + minimal JSON; golden-file comparison against expected DTS snippets |
| Stage 4 (`merger.py`) | Unit tests with small synthetic base DTS strings |
| Stage 5 (`visualizer.py`) | Smoke test — validates HTML is well-formed, D3 bundle present, expected node names appear |
| End-to-end | `@pytest.mark.hw` test in `test/hw/` — full pipeline against a real XSA, deploy to hardware via labgrid; skipped in CI |

---

## Dependencies

Add optional dependency group `[xsa]` to `pyproject.toml`:

```toml
[project.optional-dependencies]
xsa = ["lopper"]  # provides sdtgen entry point
```

`adidt/xsa/d3_bundle.js` — D3.js v7.9.0 minified, committed to repo. Regenerate via `scripts/embed_d3.py`.

---

## References

- [ADI JESD204 FSM Framework](https://wiki.analog.com/resources/tools-software/linux-drivers/jesd204/jesd204-fsm-framework)
- [Lopper / sdtgen](https://github.com/devicetree-org/lopper)
- `adidt/boards/layout.py` — `map_clocks_to_board_layout()` pattern to replace in XSA flow
- `adidt/templates/` — Jinja2 template conventions to follow
- `adidt/cli/main.py` — existing Click `cli` group to register `xsa2dt` on
