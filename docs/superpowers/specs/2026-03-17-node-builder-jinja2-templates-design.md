# node_builder.py — Jinja2 Template Migration Design

**Date:** 2026-03-17
**Status:** Approved

## Problem

`adidt/xsa/node_builder.py` is ~2,800 lines. The five board-specific builders
(`_build_fmcdaq2_nodes`, `_build_fmcdaq3_nodes`, `_build_ad9172_nodes`,
`_build_ad9081_nodes`, `_build_adrv9009_nodes`) account for ~1,650 of those
lines. Nearly all of that bulk is f-string DTS generation — Python string
concatenation that is hard to read, hard to edit, and must be understood as
both Python and DTS simultaneously. Adding a new board means copying hundreds
of lines of string-building boilerplate.

## Goal

Move all DTS string generation out of Python and into Jinja2 template files.
Python keeps all logic (config extraction, clock resolution, label inference,
frequency computation). Templates contain only DTS text, `{{ variable }}`
substitutions, and simple `{% if %}` / `{% for %}` blocks.

## Scope

**In scope:** Replace f-string DTS generation in the five board builders and
their associated channel-block helper methods.

**Out of scope:** The existing `clkgen.tmpl`, `jesd204_fsm.tmpl`, and
`axi_ad9081.tmpl` templates are already well-structured and are not changed.
The `build()` dispatch method, all cfg dataclasses, all non-string logic, and
the public API of `NodeBuilder` are unchanged.

DMA nodes (`&axi_*_dma { compatible = "adi,axi-dmac-1.00.a"; ... }`) are four
lines each with no variable content beyond the label. They remain as Python
f-strings — a template adds no value.

## Approach

One Jinja2 template per chip/peripheral type. Each template renders all DTS
nodes associated with that chip. Python board builders compute context dicts
from already-extracted cfg dataclasses, then call `_render(template, ctx)` for
each chip in the board. Templates are small, focused, and reusable across
boards.

## New Template Files

All templates live in `adidt/templates/xsa/`.

### Clock chips

| File | Renders | Used by |
|------|---------|---------|
| `hmc7044.tmpl` | HMC7044 node + channel sub-nodes | AD9172, AD9081, ADRV9009/FMComms8 |
| `ad9523_1.tmpl` | AD9523-1 node + channel sub-nodes | fmcdaq2 |
| `ad9528.tmpl` | AD9528 node + channel sub-nodes | fmcdaq3 |
| `ad9528_1.tmpl` | AD9528-1 node + channel sub-nodes | ADRV9009 |

### Data converters

| File | Renders | Used by |
|------|---------|---------|
| `ad9680.tmpl` | AD9680 device node | fmcdaq2, fmcdaq3 |
| `ad9144.tmpl` | AD9144 device node | fmcdaq2 |
| `ad9152.tmpl` | AD9152 device node | fmcdaq3 |
| `ad9172.tmpl` | AD9172 device node | AD9172 |
| `adrv9009.tmpl` | ADRV9009 device node | ADRV9009 |
| `ad9081_mxfe.tmpl` | AD9081 MxFE device node + tx-dacs/rx-adcs sub-trees | AD9081 |

### Shared FPGA overlay nodes

| File | Renders | Used by |
|------|---------|---------|
| `adxcvr.tmpl` | `&axi_*_adxcvr { ... }` overlay | fmcdaq2, fmcdaq3, AD9172, AD9081, ADRV9009 |
| `jesd204_overlay.tmpl` | Board-specific JESD204 overlay (extended properties) | fmcdaq2, fmcdaq3, AD9172, AD9081, ADRV9009 |
| `tpl_core.tmpl` | `&*_tpl_core { ... }` DMA/JESD overlay | fmcdaq2, fmcdaq3, AD9172, AD9081 |

**Total: 13 new template files.**

Note: `jesd204_overlay.tmpl` is distinct from `jesd204_fsm.tmpl`. The FSM
template renders bus-instantiated JESD nodes (new nodes in the bus). The
overlay template renders `&label { ... }` overlays that patch existing nodes
with board-specific clock references and properties.

## Context Contracts

### `hmc7044.tmpl`

```python
{
    "label": str,                    # e.g. "hmc7044"
    "cs": int,
    "spi_max_hz": int,
    "pll1_clkin_frequencies": list[int],
    "vcxo_hz": int,
    "pll2_output_hz": int,
    "clock_output_names": list[str],
    "jesd204_sysref_provider": bool,
    "jesd204_max_sysref_hz": int,
    # Optional — omitted keys produce no output line:
    "pll1_loop_bandwidth_hz": int | None,
    "pll1_ref_prio_ctrl": str | None,    # e.g. "0xE1"
    "pll1_ref_autorevert": bool,
    "pll1_charge_pump_ua": int | None,
    "pfd1_max_freq_hz": int | None,
    "sysref_timer_divider": int | None,
    "pulse_generator_mode": int | None,
    "clkin0_buffer_mode": str | None,
    "clkin1_buffer_mode": str | None,
    "oscin_buffer_mode": str | None,
    "gpi_controls": list[int],
    "gpo_controls": list[int],
    "sync_pin_mode": int | None,
    "high_perf_mode_dist_enable": bool,
    # Exactly one of channels/raw_channels is non-None at any call site:
    "channels": [                    # Normal path: Python-built list rendered via {% for %}
        {
            "id": int,
            "name": str,
            "divider": int,
            "freq_str": str,             # pre-computed by _fmt_hz(), e.g. "250 MHz"
            "driver_mode": int,
            "coarse_digital_delay": int | None,
            "startup_mode_dynamic": bool,
            "high_perf_mode_disable": bool,
            "is_sysref": bool,           # emits adi,jesd204-sysref-chan
        },
        ...
    ] | None,
    "raw_channels": str | None,      # Override path: pre-rendered DTS channel block string
                                     # (from hmc7044_channel_blocks config key via _format_nested_block).
                                     # Template: {% if channels %}...{% for %}...{% else %}{{ raw_channels }}{% endif %}
}
```

**`custom_hmc7044_blocks` override:** The AD9081 and ADRV9009 builders support
a `hmc7044_channel_blocks` config key that injects raw pre-formatted DTS
channel blocks. When this key is present, Python builds the channel block
string using `_format_nested_block` (unchanged) and bypasses `hmc7044.tmpl`.
The SPI wrapper and HMC7044 chip-level properties are still rendered via the
template; only the channel sub-nodes section is overridden. The context dict
passes `channels: None` in this case, and the template emits `{{ raw_channels }}`
(a pre-rendered string) instead of iterating `{% for ch in channels %}`.

### Clock chip templates (`ad9523_1.tmpl`, `ad9528.tmpl`, `ad9528_1.tmpl`)

Similar channel-list pattern. Channels include `signal_source` (0=PLL,
2=sysref). `freq_str` is only populated when `signal_source == 0`; sysref
channels receive an empty `freq_str` and the template omits the comment.

```python
{
    "label": str,
    "cs": int,
    "spi_max_hz": int,
    "vcxo_hz": int,
    "clock_output_names": list[str],
    # chip-specific PLL config fields (vary per chip):
    #   ad9523_1: "pll1_charge_pump_current", "pll2_charge_pump_current",
    #             "pll2_ndiv_a_cnt", "pll2_ndiv_b_cnt", "pll2_r2_div",
    #             "pll2_vco_diff_m1", "pll2_vco_diff_m2"
    #   ad9528: "pll1_feedback_div_ratio", "pll2_vco_output_div",
    #           "pll2_charge_pump_current_ua"
    #   ad9528_1: same shape as ad9528; written as a separate template
    #             to allow per-chip property differences without conditionals
    "channels": [
        {
            "id": int,
            "name": str,
            "channel_divider": int,
            "freq_str": str,             # empty string for sysref channels
            "driver_mode": int,
            "divider_phase": int,
            "signal_source": int,        # 0=PLL, 2=sysref
            "is_sysref": bool,
        },
        ...
    ],
}
```

**AD9528 vs AD9528-1 distinction:** `ad9528.tmpl` (fmcdaq3) and
`ad9528_1.tmpl` (ADRV9009) use identical context schema but different
chip-level property names. Having two templates avoids in-template conditionals
for structural differences while sharing the same Python context builder
signature.

### `adxcvr.tmpl`

The adxcvr node has two hardware variants; a single template handles both via
conditionals:

- **2-clock variant** (fmcdaq2 only): `clocks = <&clk N>, <&clk N>;
  clock-names = "conv", "div40";` plus `adi,jesd-l/m/s` JESD parameters;
  no `jesd204-inputs`; `use_lpm_enable=True`.
- **1-clock variant** (fmcdaq3, AD9172, AD9081, ADRV9009): `clocks = <&clk N>;
  clock-names = "conv";` no JESD L/M/S parameters.
  `use_lpm_enable=True` for fmcdaq3 and AD9172; `False` for AD9081 only.

`jesd204_inputs` for the 1-clock variant:
- fmcdaq3 **RX** adxcvr: literal constant `"&clk0_ad9528 0 0"` (hardcoded)
- fmcdaq3 **TX** adxcvr: `None` — this node does **not** emit `jesd204-inputs` at all (see builder lines 819–830)
- AD9172: literal constant `"&hmc7044 0 0"` (hardcoded)
- AD9081: `f"&hmc7044 0 {rx_link_id}"` or `f"&hmc7044 0 0"` (dynamic link_id from cfg)

The template must guard `jesd204-inputs` with `{% if jesd204_inputs %}` even in the 1-clock code path.

```python
{
    "label": str,                    # e.g. "axi_ad9680_adxcvr"
    "sys_clk_select": int,
    "out_clk_select": int,
    "clk_ref": str,                  # e.g. "&clk0_ad9523 4"
    "use_div40": bool,               # True for fmcdaq2; adds div40 clock entry
    "div40_clk_ref": str | None,     # populated when use_div40=True
    "clock_output_names": list[str], # e.g. ["adc_gt_clk", "rx_out_clk"]
    "use_lpm_enable": bool,          # True for fmcdaq2, fmcdaq3, and AD9172; False for AD9081 only
    # JESD L/M/S — only emitted when use_div40=True (fmcdaq2)
    "jesd_l": int | None,
    "jesd_m": int | None,
    "jesd_s": int | None,
    # jesd204-inputs — only emitted when use_div40=False
    "jesd204_inputs": str | None,    # e.g. "&hmc7044 0 2"
    "is_rx": bool,
}
```

### `jesd204_overlay.tmpl`

The overlay renders `&label { ... }` patches for JESD204 TX and RX AXI
instances. TX nodes carry additional framing metadata fields; all are optional
to allow the same template to serve both directions.

```python
{
    "label": str,                    # e.g. "axi_ad9680_jesd204_rx"
    "direction": str,                # "rx" or "tx"
    "clocks": list[str],             # e.g. ["&zynqmp_clk 71", "&clk0_ad9523 13", "&axi_ad9680_adxcvr 0"]
    "clock_names": list[str],        # e.g. ["s_axi_aclk", "device_clk", "lane_clk"]
    "clock_output_name": str | None,  # e.g. "jesd_adc_lane_clk"; None for AD9081 RX/TX and ADRV9009 RX/TX.
                                     # #clock-cells = <0> is ALWAYS emitted unconditionally (present in all boards
                                     # including AD9081). Only clock-output-names is guarded by
                                     # {% if clock_output_name %} — do NOT put #clock-cells inside that guard.
    "f": int,                        # adi,octets-per-frame
    "k": int,                        # adi,frames-per-multiframe
    "jesd204_inputs": str,           # e.g. "&axi_ad9680_adxcvr 0 0"; always populated — never None
                                     # (unlike adxcvr.tmpl where this field is nullable)
    # TX-only optional fields — omitted for RX
    # converters_per_device, bits_per_sample, control_bits_per_sample: populated by ALL TX callers
    # (fmcdaq2 TX, fmcdaq3 TX, AD9172 TX, AD9081 TX); pass None only for RX direction.
    "converter_resolution": int | None,      # present for fmcdaq2 TX (value 14) and ADRV9009 TX (hardcoded 14); None for fmcdaq3 TX, AD9172 TX, AD9081 TX
    "converters_per_device": int | None,     # populated by all TX callers; None for RX
    "bits_per_sample": int | None,           # populated by all TX callers; None for RX
    "control_bits_per_sample": int | None,   # populated by all TX callers; None for RX
}
```

### `tpl_core.tmpl`

Renders the TPL core overlay node. DMA-related fields are absent for AD9172,
which has no dedicated DMA node attached to its TPL core.

```python
{
    "label": str,                    # e.g. "axi_ad9680_core"
    "compatible": str,               # e.g. "adi,axi-ad9680-1.0"
    "direction": str,                # "rx" or "tx"
    "dma_label": str | None,         # None for AD9172 (no DMA); when None, both dmas and dma-names lines are suppressed
    "spibus_label": str,             # device label for spibus-connected, e.g. "adc0_ad9680"
    "jesd_label": str,
    "jesd_link_offset": int,         # first arg of jesd204-inputs phandle: 0 for RX; 1 for TX on fmcdaq2/fmcdaq3; 0 for TX on AD9172 and AD9081
    "link_id": int,                  # second arg of jesd204-inputs phandle (e.g. adc_jesd_link_id)
                                     # renders as: jesd204-inputs = <&{jesd_label} {jesd_link_offset} {link_id}>
    "pl_fifo_enable": bool,          # False for all RX cores and for AD9081 TX; True for fmcdaq2 TX, fmcdaq3 TX, and AD9172 TX only
    # AD9081 TX only — clocks from sampl_clk output
    "sampl_clk_ref": str | None,     # e.g. "trx0_ad9081 1"; None for all other cores.
                                     # The "1" is the fixed port index of tx_sampl_clk in
                                     # ad9081_mxfe's hardcoded clock-output-names array; not a config variable.
    "sampl_clk_name": str | None,    # e.g. "sampl_clk"; None for all other cores
}
```

### `ad9081_mxfe.tmpl`

Renders the `trx0_ad9081` device node with its complete `adi,tx-dacs` and
`adi,rx-adcs` sub-trees. The node appears inside an SPI bus overlay handled by
`_wrap_spi_bus`.

```python
{
    "label": str,               # "trx0_ad9081"
    "cs": int,
    "spi_max_hz": int,          # 5000000
    "gpio_label": str,          # e.g. "gpio"
    "reset_gpio": int,
    "sysref_req_gpio": int,
    "rx2_enable_gpio": int,
    "rx1_enable_gpio": int,
    "tx2_enable_gpio": int,
    "tx1_enable_gpio": int,
    "dev_clk_ref": str,         # e.g. "hmc7044 2"
    # Template constants (not parameterised, but must appear in template):
    #   #clock-cells = <1>;
    #   clock-output-names = "rx_sampl_clk", "tx_sampl_clk";
    #   In jesd204-inputs: <&{rx_core_label} 0 {rx_link_id}>, <&{tx_core_label} 0 {tx_link_id}>
    #     — the port index 0 for both RX-core and TX-core is a fixed constant, not a context variable.
    #   In JESD link sub-nodes (both tx-dacs and rx-adcs):
    #     adi,converter-resolution = <16>;
    #     adi,bits-per-sample = <16>;
    #     adi,control-bits-per-sample = <0>;
    #     — these are hardcoded constants, not parameterised.
    "rx_core_label": str,
    "tx_core_label": str,
    "rx_link_id": int,
    "tx_link_id": int,
    # tx-dacs sub-tree
    "dac_frequency_hz": int,
    "tx_cduc_interpolation": int,
    "tx_fduc_interpolation": int,
    "tx_converter_select": str,  # pre-formatted, e.g. "<0x00> <0xFF> ..."
    "tx_lane_map": str,          # pre-formatted byte sequence
    "tx_link_mode": int,
    "tx_m": int,
    "tx_f": int,
    "tx_k": int,
    "tx_l": int,
    "tx_s": int,
    # rx-adcs sub-tree
    "adc_frequency_hz": int,
    "rx_cddc_decimation": int,
    "rx_fddc_decimation": int,
    "rx_converter_select": str,
    "rx_lane_map": str,
    "rx_link_mode": int,
    "rx_m": int,
    "rx_f": int,
    "rx_k": int,
    "rx_l": int,
    "rx_s": int,
}
```

### Converter templates (`ad9680.tmpl`, `ad9144.tmpl`, etc.)

Each converter template renders the device node that sits inside an SPI bus
overlay. The SPI bus wrapper itself is handled by Python (`_wrap_spi_bus`).

```python
{
    "label": str,
    "cs": int,
    "spi_max_hz": int,
    "clocks": list[str],
    "clock_names": list[str],
    # JESD204 linkage
    "jesd204_top_device": int | None,
    "jesd204_link_ids": list[int],
    "jesd204_inputs": str,
    # converter parameters (vary per device)
    "m": int, "l": int, "f": int, "k": int, "np": int,
    # optional GPIO lines
    "gpio_lines": list[{"prop": str, "controller": str, "index": int}],
}
```

## Python Changes

### New private context-builder methods

One per chip type, called by board builders:

- `_build_hmc7044_ctx(label, cs, pll_cfg, channels_spec) -> dict`
- `_build_hmc7044_channel_ctx(pll2_hz, channels_spec) -> list[dict]`
  — pre-computes `freq_str` for each channel using `_fmt_hz`
- `_build_ad9523_1_ctx(fmc: _FMCDAQ2Cfg) -> dict`
- `_build_ad9528_ctx(fmc: _FMCDAQ3Cfg) -> dict`
- `_build_ad9528_1_ctx(board_cfg, vcxo_hz) -> dict`
- `_build_adxcvr_ctx(cfg, direction) -> dict`
- `_build_jesd204_overlay_ctx(cfg, direction) -> dict`
- `_build_tpl_core_ctx(cfg, direction) -> dict`
- `_build_ad9680_ctx(fmc, ps_clk_label, ps_clk_index) -> dict`
- `_build_ad9144_ctx(fmc, ps_clk_label, ps_clk_index) -> dict`
- `_build_ad9152_ctx(fmc, ps_clk_label, ps_clk_index) -> dict`
- `_build_ad9172_device_ctx(ad) -> dict`
- `_build_adrv9009_device_ctx(...) -> dict`
- `_build_ad9081_mxfe_ctx(...) -> dict`

### Board builder shape (after)

```python
def _build_fmcdaq2_nodes(self, topology, cfg, ps_clk_label, ps_clk_index):
    if not topology.is_fmcdaq2_design():
        return []
    fmc = self._build_fmcdaq2_cfg(cfg)
    spi_children = (
        self._render("ad9523_1.tmpl", self._build_ad9523_1_ctx(fmc))
        + self._render("ad9680.tmpl",  self._build_ad9680_ctx(fmc, ps_clk_label, ps_clk_index))
        + self._render("ad9144.tmpl",  self._build_ad9144_ctx(fmc, ps_clk_label, ps_clk_index))
    )
    return [
        self._wrap_spi_bus(fmc.spi_bus, spi_children),
        self._render("adxcvr.tmpl",          self._build_adxcvr_ctx(fmc, "rx")),
        self._render("adxcvr.tmpl",          self._build_adxcvr_ctx(fmc, "tx")),
        self._render("jesd204_overlay.tmpl", self._build_jesd204_overlay_ctx(fmc, "rx")),
        self._render("jesd204_overlay.tmpl", self._build_jesd204_overlay_ctx(fmc, "tx")),
        self._render("tpl_core.tmpl",        self._build_tpl_core_ctx(fmc, "rx")),
        self._render("tpl_core.tmpl",        self._build_tpl_core_ctx(fmc, "tx")),
        f"\t&{fmc.adc_dma_label} {{\n\t\tcompatible = \"adi,axi-dmac-1.00.a\";\n\t\t#dma-cells = <1>;\n\t\t#clock-cells = <0>;\n\t}};",
        f"\t&{fmc.dac_dma_label} {{\n\t\tcompatible = \"adi,axi-dmac-1.00.a\";\n\t\t#dma-cells = <1>;\n\t\t#clock-cells = <0>;\n\t}};",
    ]
```

DMA nodes remain as Python f-strings in the builder — they are four lines with
no variable content beyond the label.

### New utility methods

```python
def _render(self, template_name: str, ctx: dict) -> str:
    """Render a Jinja2 template from adidt/templates/xsa/ with the given context."""
    return self._env.get_template(template_name).render(ctx)

def _wrap_spi_bus(self, label: str, children: str) -> str:
    """Wrap pre-rendered child node strings in a &label { status = "okay"; ... } overlay.

    Produces:
        \t&label {
        \t\tstatus = "okay";
        <children>
        \t};
    """
```

### `_env` property and existing render methods

`_make_jinja_env` is refactored into a cached `_env` property used by both
`_render` and the existing `_render_clkgen`, `_render_jesd`, and
`_render_converter` methods. Those three methods are **not changed** — they
continue to call `self._env.get_template(...)` internally. The `_env` property
replaces the `_make_jinja_env()` call at the point those methods previously
invoked it.

### What is removed

The following methods are deleted after all callers are migrated:
- `_fmcdaq2_ad9523_channels_block()`
- `_fmcdaq3_ad9528_channels_block()`
- The `default_hmc7044_channels_block` string variables in `_build_ad9081_nodes`
  and `_build_adrv9009_nodes`

All inline f-string DTS generation within the five board builders is removed.

## Key Invariants

- **No logic in templates.** Conditionals in templates are only for optional
  property emission (`{% if ctx.foo is not none %}`). All values are
  pre-computed in Python.
- **Frequency strings pre-computed.** `_fmt_hz()` is called in Python context
  builders, never inside templates.
- **Output must be byte-for-byte identical.** The refactor is pure
  restructuring; no DTS content changes.
- **`build()` dispatch is unchanged.** All five board builders keep the same
  signature and return type.

## Testing

### Existing tests (unchanged, regression-only)

`test_node_builder.py`, `test_node_builder_fmcdaq3.py`,
`test_node_builder_ad9172.py`, and the pipeline golden snapshot test
(`test_pipeline_merged_matches_golden_snapshot`) all assert on full rendered
DTS output. These pass without modification if the refactor is correct.

### New tests

`test/xsa/test_node_builder_templates.py` — one parameterized test per
template. Each test renders the template with a minimal known-good context dict
and asserts that key DTS properties appear in the output:

```python
def test_hmc7044_template_renders_channel_with_freq_comment():
    # All required fields must be provided; abbreviated here for illustration.
    ctx = {
        "label": "hmc7044", "cs": 0, "spi_max_hz": 1000000,
        "pll1_clkin_frequencies": [122880000, 0, 0, 0],
        "vcxo_hz": 122880000,
        "pll2_output_hz": 3_000_000_000,
        "clock_output_names": [f"hmc7044_out{i}" for i in range(14)],
        "jesd204_sysref_provider": True,
        "jesd204_max_sysref_hz": 2000000,
        # optional fields — pass None to suppress
        "pll1_loop_bandwidth_hz": None, "pll1_ref_prio_ctrl": None,
        "pll1_ref_autorevert": False, "pll1_charge_pump_ua": None,
        "pfd1_max_freq_hz": None, "sysref_timer_divider": None,
        "pulse_generator_mode": None, "clkin0_buffer_mode": None,
        "clkin1_buffer_mode": None, "oscin_buffer_mode": None,
        "gpi_controls": [], "gpo_controls": [],
        "sync_pin_mode": None, "high_perf_mode_dist_enable": False,
        "channels": [{"id": 2, "name": "DEV_REFCLK", "divider": 12,
                      "freq_str": "250 MHz", "driver_mode": 2,
                      "coarse_digital_delay": None, "startup_mode_dynamic": False,
                      "high_perf_mode_disable": False, "is_sysref": False}],
        "raw_channels": None,
    }
    out = NodeBuilder()._render("hmc7044.tmpl", ctx)
    assert 'adi,divider = <12>; // 250 MHz' in out
    assert 'adi,extended-name = "DEV_REFCLK"' in out
```

`test/xsa/test_node_builder_context_builders.py` — unit tests for each
context-builder method. Each test calls `_build_<chip>_ctx(...)` with a
minimal cfg/dataclass and asserts that the returned dict has the expected
keys and values. These tests are independent of template rendering and run
without filesystem I/O.

Tests are fast (no filesystem I/O beyond template loading) and isolated.

## Migration Order

Migrate one board builder at a time, running the full test suite after each:

1. `_build_ad9172_nodes` — smallest builder, simplest HMC7044 usage; establishes `hmc7044.tmpl` and `ad9172.tmpl`. Note: AD9172 uses a static 4-channel HMC7044 block with no cfg-driven optional fields (`pll1_ref_prio_ctrl`, `clkin1_buffer_mode`, etc. all `None`). The full optional-field coverage of `hmc7044.tmpl` is exercised in step 4 (AD9081) and step 5 (ADRV9009). Write template conditionals for those optional fields in step 1, even though they are not exercised until later steps.
2. `_build_fmcdaq2_nodes` — establishes `ad9523_1.tmpl`, `ad9680.tmpl`, `ad9144.tmpl`, `adxcvr.tmpl`, `jesd204_overlay.tmpl`, `tpl_core.tmpl`
3. `_build_fmcdaq3_nodes` — reuses most templates from step 2; adds `ad9528.tmpl`, `ad9152.tmpl`
4. `_build_ad9081_nodes` — reuses `hmc7044.tmpl`; adds `ad9081_mxfe.tmpl`
5. `_build_adrv9009_nodes` — largest; reuses `hmc7044.tmpl`; adds `ad9528_1.tmpl`, `adrv9009.tmpl`
