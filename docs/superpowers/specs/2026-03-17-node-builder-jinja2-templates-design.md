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
| `adxcvr.tmpl` | `&axi_*_adxcvr { ... }` overlay | fmcdaq2, fmcdaq3, AD9172 |
| `jesd204_overlay.tmpl` | Board-specific JESD204 overlay (extended properties) | fmcdaq2, fmcdaq3 |
| `tpl_core.tmpl` | `&*_tpl_core { ... }` DMA/JESD overlay | fmcdaq2, fmcdaq3 |

**Total: 13 new template files.**

Note: `jesd204_overlay.tmpl` is distinct from `jesd204_fsm.tmpl`. The FSM
template renders bus-instantiated JESD nodes (new nodes in the bus). The
overlay template renders `&label { ... }` overlays that patch existing nodes
with board-specific clock references and properties, as used by fmcdaq2/3.

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
    "channels": [
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
    ],
}
```

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
    # chip-specific PLL config fields (vary per chip)
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

### `adxcvr.tmpl`

```python
{
    "label": str,                    # e.g. "axi_ad9680_adxcvr"
    "sys_clk_select": int,
    "out_clk_select": int,
    "clk_ref": str,                  # e.g. "&clk0_ad9523 4"
    "div40_clk_ref": str,
    "num_lanes": int,
    "is_rx": bool,
}
```

### `jesd204_overlay.tmpl`

```python
{
    "label": str,                    # e.g. "axi_ad9680_jesd204_rx"
    "direction": str,                # "rx" or "tx"
    "clocks": list[str],             # e.g. ["&zynqmp_clk 71", "&clk0_ad9523 13"]
    "clock_names": list[str],
    "xcvr_label": str,
    "link_id": int,
}
```

### `tpl_core.tmpl`

```python
{
    "label": str,                    # e.g. "axi_ad9680_core"
    "direction": str,
    "dma_label": str,
    "jesd_label": str,
    "compatible": str,
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
    ]
```

### New utility methods

```python
def _render(self, template_name: str, ctx: dict) -> str:
    """Render a Jinja2 template from adidt/templates/xsa/ with the given context."""

def _wrap_spi_bus(self, label: str, children: str) -> str:
    """Wrap pre-rendered child node strings in a &label { status = "okay"; ... } overlay."""
```

`_make_jinja_env` is refactored into a cached `_env` property used by `_render`.

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
    ctx = {
        "label": "hmc7044", "cs": 0, "spi_max_hz": 1000000,
        "pll2_output_hz": 3_000_000_000,
        "channels": [{"id": 2, "name": "DEV_REFCLK", "divider": 12,
                      "freq_str": "250 MHz", "driver_mode": 2,
                      "is_sysref": False, ...}],
        ...
    }
    out = NodeBuilder()._render("hmc7044.tmpl", ctx)
    assert 'adi,divider = <12>; // 250 MHz' in out
    assert 'adi,extended-name = "DEV_REFCLK"' in out
```

Tests are fast (no filesystem I/O beyond template loading) and isolated.

## Migration Order

Migrate one board builder at a time, running the full test suite after each:

1. `_build_ad9172_nodes` — smallest builder, simplest HMC7044 usage; establishes `hmc7044.tmpl` and `ad9172.tmpl`
2. `_build_fmcdaq2_nodes` — establishes `ad9523_1.tmpl`, `ad9680.tmpl`, `ad9144.tmpl`, `adxcvr.tmpl`, `jesd204_overlay.tmpl`, `tpl_core.tmpl`
3. `_build_fmcdaq3_nodes` — reuses most templates from step 2; adds `ad9528.tmpl`, `ad9152.tmpl`
4. `_build_ad9081_nodes` — reuses `hmc7044.tmpl`; adds `ad9081_mxfe.tmpl`
5. `_build_adrv9009_nodes` — largest; reuses `hmc7044.tmpl`; adds `ad9528_1.tmpl`, `adrv9009.tmpl`
