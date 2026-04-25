# XSA → Device Tree: AD9081 on ZCU102

This example walks through the full XSA-to-overlay pipeline for the
**AD9081-FMCA-EBZ** evaluation board on the **ZCU102** (Zynq UltraScale+).

The script lives at `examples/xsa/ad9081_zcu102_xsa_parse.py` and uses
`examples/xsa/system_top.xsa` — the Vivado 2023.2 reference design bitfile
for this board.

## Design Overview

| Item | Value |
|------|-------|
| FPGA | xczu9eg-ffvb1156-2 (ZCU102) |
| Converter | AD9081 (MxFE), SPI-controlled |
| JESD204 RX | `axi_mxfe_rx_jesd_rx_axi` – 4 lanes, `0x84A90000`, IRQ 54 |
| JESD204 TX | `axi_mxfe_tx_jesd_tx_axi` – 4 lanes, `0x84B90000`, IRQ 55 |
| JESD mode | 204B, M=8 L=4 S=1 Np=16 → **F=4, K=32** |
| Clock gen | HMC7044 external – RX ch 12, TX ch 13 |

## Prerequisites

```bash
pip install "adidt[xsa]"
pip install pyadi-jif[cplex]   # or [gekko] – solver only needed for clock opt
```

## Running the Example

```bash
python examples/xsa/ad9081_zcu102_xsa_parse.py
```

Expected output:

```
============================================================
AD9081 + ZCU102: XSA → Device Tree overlay
============================================================

Step 1 – Parsing XSA …
  FPGA part  : xczu9eg-ffvb1156-2
  JESD RX    : axi_mxfe_rx_jesd_rx_axi  base=0x84a90000  lanes=4
  JESD TX    : axi_mxfe_tx_jesd_tx_axi  base=0x84b90000  lanes=4
  Clock gen  : hmc7044_car  clocks=[...]

Step 2 – Resolving JESD204 parameters via adijif …
JESD mode (RX): mode=10.0  F=4 K=32 L=4 M=8
JESD mode (TX): mode=9     F=4 K=32 L=4 M=8

Step 3 – Generating DTS overlay …
Overlay written to: examples/xsa/output/ad9081_zcu102.dtso
```

## Generated Overlay

`examples/xsa/output/ad9081_zcu102.dtso`:

```dts
/dts-v1/;
/plugin/;

&amba {

	axi_mxfe_rx_jesd_rx_axi: axi-jesd204-rx@84a90000 {
		compatible = "adi,axi-jesd204-rx-1.0";
		reg = <0x0 0x84a90000 0x0 0x1000>;
		interrupts = <0 54 IRQ_TYPE_LEVEL_HIGH>;
		clocks = <&hmc7044_car 0>, <&hmc7044 12>, <&hmc7044_car 1>;
		clock-names = "s_axi_aclk", "device_clk", "lane_clk";

		adi,octets-per-frame = <4>;
		adi,frames-per-multiframe = <32>;

		#sound-dai-cells = <0>;
	};

	axi_mxfe_tx_jesd_tx_axi: axi-jesd204-tx@84b90000 {
		compatible = "adi,axi-jesd204-tx-1.0";
		reg = <0x0 0x84b90000 0x0 0x1000>;
		interrupts = <0 55 IRQ_TYPE_LEVEL_HIGH>;
		clocks = <&hmc7044_car 0>, <&hmc7044 13>, <&hmc7044_car 1>;
		clock-names = "s_axi_aclk", "device_clk", "lane_clk";

		adi,octets-per-frame = <4>;
		adi,frames-per-multiframe = <32>;

		#sound-dai-cells = <0>;
	};
};
```

## Pipeline Walkthrough

### Step 1 – Parse and patch the XSA

`XsaParser.parse()` extracts `axi_jesd204_rx` and `axi_jesd204_tx` modules
from the hardware handoff XML embedded in the XSA ZIP archive.

The Vivado 2023.2 HWH uses a slightly older schema than the parser's primary
fixture. The script patches the topology with the correct values:

| Field | Parser reads | Actual HWH element | Patched value |
|-------|--------------|--------------------|---------------|
| `fpga_part` | `<DEVICE>` child | `<SYSTEMINFO DEVICE="...">` attr | `xczu9eg-ffvb1156-2` |
| `num_lanes` | `C_NUM_LANES` param | `NUM_LANES` param | 4 |
| `base_addr` | `<MEMRANGE>` child | `C_BASEADDR` param | `0x84A90000` / `0x84B90000` |
| `irq` | port named `interrupt` | port named `irq` | 54 / 55 |

A synthetic `ClkgenInstance` named `hmc7044_car` is added so `NodeBuilder`
can resolve the device-clock nets to a DTS label. The HMC7044 drives both
clocks externally — there is no `axi_clkgen` in this design.

### Step 2 – Resolve JESD204 parameters with adijif

```python
import adijif as jif

sys = jif.system("ad9081", "hmc7044", "xilinx", 122.88e6, solver="CPLEX")
sys.fpga.setup_by_dev_kit_name("zcu102")
sys.converter.adc.sample_clock = 4e9 / (4 * 4)   # 250 MSPS
sys.converter.dac.sample_clock = 12e9 / (8 * 6)  # 250 MSPS
# … configure datapath …

modes_rx = jif.utils.get_jesd_mode_from_params(
    sys.converter.adc, M=8, L=4, S=1, Np=16, jesd_class="jesd204b"
)
# → mode 10.0: F=4, K=32
```

`get_jesd_mode_from_params` performs a pure table lookup against the AD9081
operating modes — it does **not** invoke the constraint solver, so it works
without cpoptimizer or gekko installed.

### Step 3 – Render and write the overlay

```python
from adidt.xsa.node_builder import NodeBuilder
from adidt.xsa.merger import DtsMerger

cfg = {
    "jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}},
    "clock": {"hmc7044_rx_channel": 12, "hmc7044_tx_channel": 13},
}
nodes = NodeBuilder().build(topology, cfg)
DtsMerger().merge(base_dts, nodes, output_dir, "ad9081_zcu102")
```

`NodeBuilder` renders the Jinja2 templates (`jesd204_fsm.tmpl`) into DTS
node strings. `DtsMerger` wraps them in a `/plugin/;` overlay targeting the
`&amba` bus label.

### AD9081 link-mode selection behavior

For AD9081 MXFE pipelines, JESD link modes are no longer hardcoded. The
builder resolves mode values in this order:

1. `cfg["ad9081"]["rx_link_mode"]` / `cfg["ad9081"]["tx_link_mode"]`
2. `cfg["jesd"]["rx"]["mode"]` / `cfg["jesd"]["tx"]["mode"]`
3. Inference from JESD `(M, L)`:
   - `(8, 4)` -> RX `17`, TX `18`
   - `(4, 8)` -> RX `10`, TX `11`

If no explicit mode is provided and `(M, L)` is unsupported, generation fails
with `ConfigError` so invalid link mode assumptions are not emitted into DTS.

## Full Pipeline (with sdtgen)

When lopper is installed the `adidtc xsa2dt` command runs all five stages,
including SDT base-DTS generation and HTML visualisation:

```bash
adidtc xsa2dt examples/xsa/system_top.xsa config.json \
        --output-dir out/ad9081_zcu102
```

Where `config.json` contains:

```json
{
  "jesd": {
    "rx": { "F": 4, "K": 32 },
    "tx": { "F": 4, "K": 32 }
  },
  "clock": {
    "hmc7044_rx_channel": 12,
    "hmc7044_tx_channel": 13
  }
}
```

## Compiling the Overlay

```bash
dtc -@ -I dts -O dtb \
    -o examples/xsa/output/ad9081_zcu102.dtbo \
    examples/xsa/output/ad9081_zcu102.dtso
```

The `-@` flag preserves external symbol references (the `&amba` phandle)
required for overlay application at runtime via `configfs`.

## Loading the Overlay at Runtime

With `CONFIG_OF_OVERLAY=y` in the target kernel (the default in Kuiper
2023_R2 and later), a `.dtbo` can be applied on a running system via
`configfs`. After copying the `.dtbo` to the target (e.g. `/tmp/`):

```bash
# Apply: creates an entry, writes the path, kernel applies the overlay
mkdir -p /sys/kernel/config/device-tree/overlays/ad9081_zcu102
echo -n /tmp/ad9081_zcu102.dtbo \
    > /sys/kernel/config/device-tree/overlays/ad9081_zcu102/path

# Remove: drivers are unbound, phandles added by the overlay are torn down
rmdir /sys/kernel/config/device-tree/overlays/ad9081_zcu102
```

The hardware test `test/hw/xsa/test_ad9081_zcu102_overlay.py` exercises
the full lifecycle (load → verify JESD DATA + DMA loopback → unload →
reload) against a live ZCU102. Reuse its helpers in
`test/hw/hw_helpers.py` (`compile_dtso_to_dtbo`, `deploy_dtbo_via_shell`,
`load_overlay`, `unload_overlay`) when building your own runtime
overlay flow.
