# Node Builder Jinja2 Template Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all f-string DTS generation in the five board-specific builders with Jinja2 template files, producing byte-for-byte identical output.

**Architecture:** Thirteen new templates live in `adidt/templates/xsa/`. Python board builders call `_render(template_name, ctx)` with pre-computed context dicts. A `_wrap_spi_bus` helper handles the `&bus { status = "okay"; ... };` wrapper. All logic stays in Python; templates contain only DTS text and simple `{% if %}`/`{% for %}` substitutions.

**Tech Stack:** Python 3.10, Jinja2, pytest

---

## File Map

**New templates** (`adidt/templates/xsa/`):
- `hmc7044.tmpl` — HMC7044 device node + channels
- `ad9523_1.tmpl` — AD9523-1 device node + channels
- `ad9528.tmpl` — AD9528 device node + channels (fmcdaq3)
- `ad9528_1.tmpl` — AD9528-1 device node + channels (ADRV9009)
- `ad9680.tmpl` — AD9680 device node
- `ad9144.tmpl` — AD9144 device node
- `ad9152.tmpl` — AD9152 device node
- `ad9172.tmpl` — AD9172 device node
- `adrv9009.tmpl` — ADRV9009 device node
- `ad9081_mxfe.tmpl` — AD9081 MxFE device node + tx-dacs/rx-adcs
- `adxcvr.tmpl` — ADXCVR overlay node
- `jesd204_overlay.tmpl` — JESD204 AXI overlay node
- `tpl_core.tmpl` — TPL core overlay node

**Modified:** `adidt/xsa/node_builder.py`
- Add `_env` cached property, `_render`, `_wrap_spi_bus`
- Update `build()` and `_render_jesd`/`_render_clkgen`/`_render_converter` to use `self._env`
- Add 14 context-builder methods
- Migrate 5 board builders to use templates
- Delete `_fmcdaq2_ad9523_channels_block`, `_fmcdaq3_ad9528_channels_block`

**New tests:**
- `test/xsa/test_node_builder_templates.py` — one render test per template
- `test/xsa/test_node_builder_context_builders.py` — unit tests for context-builder methods

---

## Chunk 1: Infrastructure

### Task 1: Add `_env`, `_render`, `_wrap_spi_bus`; refactor `build()`

**Files:**
- Modify: `adidt/xsa/node_builder.py`

- [ ] **Step 1: Write failing test for `_render` and `_wrap_spi_bus`**

Add to new file `test/xsa/test_node_builder_templates.py`:

```python
# test/xsa/test_node_builder_templates.py
from adidt.xsa.node_builder import NodeBuilder


def test_render_existing_template_returns_string():
    """_render loads an existing template and returns a non-empty string."""
    nb = NodeBuilder()
    # jesd204_fsm.tmpl exists but requires specific context; pass an empty dict
    # and catch any render error — we just want AttributeError if _render doesn't exist
    result = nb._render("jesd204_fsm.tmpl", {})
    assert isinstance(result, str)


def test_wrap_spi_bus_produces_overlay():
    nb = NodeBuilder()
    result = nb._wrap_spi_bus("spi0", "\t\tchild_node;\n")
    assert "\t&spi0 {" in result
    assert 'status = "okay";' in result
    assert "\t\tchild_node;" in result
    assert "\t};" in result
```

> **Note on Step 1 test:** `test_render_existing_template_returns_string` calls `_render` directly so Step 2 fails with `AttributeError: 'NodeBuilder' object has no attribute '_render'`. The `jesd204_fsm.tmpl` template requires context variables so passing `{}` may produce a Jinja2 `UndefinedError` rather than returning a valid string — that is acceptable at this stage since the test is only checking that `_render` is callable. Alternatively use a minimal custom fixture template; the important thing is the test calls `_render`, not just `_env`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/tcollins/dev/pyadi-dt-xsa-powers
nox -s tests -- test/xsa/test_node_builder_templates.py -v
```

Expected: `AttributeError: 'NodeBuilder' object has no attribute '_render'`

- [ ] **Step 3: Add `_env` property, `_render`, `_wrap_spi_bus` to `NodeBuilder`**

In `adidt/xsa/node_builder.py`, after the `_make_jinja_env` method, add:

```python
@property
def _env(self) -> "Environment":
    """Cached Jinja2 environment for the XSA template directory."""
    if not hasattr(self, "_env_cache"):
        self._env_cache = self._make_jinja_env()
    return self._env_cache

def _render(self, template_name: str, ctx: dict) -> str:
    """Render a Jinja2 template from adidt/templates/xsa/ with the given context."""
    return self._env.get_template(template_name).render(ctx)

def _wrap_spi_bus(self, label: str, children: str) -> str:
    """Wrap pre-rendered child node strings in an &label { status = "okay"; ... } overlay."""
    return (
        f"\t&{label} {{\n"
        '\t\tstatus = "okay";\n'
        f"{children}"
        "\t};"
    )
```

Also update `build()` and the three private render methods to use `self._env` instead of the `env` local variable. Apply these changes:

**In `build()` (line 167):** Remove `env = self._make_jinja_env()`. Remove `env` as the first argument from all three call sites:
- Line 200: `self._render_clkgen(clkgen, ps_clk_label, ps_clk_index)`
- Lines 217–228: `self._render_jesd(inst, cfg.get("jesd", {}).get("rx", {}), ...)`
- Lines 246–257: `self._render_jesd(inst, cfg.get("jesd", {}).get("tx", {}), ...)`
- Line 273: `self._render_converter(conv, rx_label, tx_label)`

**Update `_render_jesd` signature (line 1501):** Remove `env: Environment` parameter; replace `env.get_template(...)` on line 1520 with `self._env.get_template(...)`.

**Update `_render_converter` signature (line 1532):** Remove `env: Environment` parameter; replace `env.get_template(...)` on lines 1539 and 1542 with `self._env.get_template(...)`.

**Update `_render_clkgen` signature (line 1550):** Remove `env: Environment` parameter; replace `env.get_template(...)` on line 1558 with `self._env.get_template(...)`.

- [ ] **Step 4: Run tests to verify infrastructure passes and existing tests still pass**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py test/xsa/test_node_builder.py test/xsa/test_node_builder_ad9172.py test/xsa/test_node_builder_fmcdaq3.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/node_builder.py test/xsa/test_node_builder_templates.py
git commit -m "xsa: add _env property, _render, _wrap_spi_bus to NodeBuilder"
```

---

## Chunk 2: AD9172 Migration

### Task 2: `hmc7044.tmpl` + context builders

**Files:**
- Create: `adidt/templates/xsa/hmc7044.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`
- Create: `test/xsa/test_node_builder_context_builders.py`

- [ ] **Step 1: Write failing template render test**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def test_hmc7044_template_renders_channel_with_freq_comment():
    ctx = {
        "label": "hmc7044",
        "cs": 0,
        "spi_max_hz": 1000000,
        "pll1_clkin_frequencies": [122880000, 0, 0, 0],
        "vcxo_hz": 122880000,
        "pll2_output_hz": 3_000_000_000,
        "clock_output_names": [f"hmc7044_out{i}" for i in range(14)],
        "jesd204_sysref_provider": True,
        "jesd204_max_sysref_hz": 2000000,
        "pll1_loop_bandwidth_hz": None,
        "pll1_ref_prio_ctrl": None,
        "pll1_ref_autorevert": False,
        "pll1_charge_pump_ua": None,
        "pfd1_max_freq_hz": None,
        "sysref_timer_divider": None,
        "pulse_generator_mode": None,
        "clkin0_buffer_mode": None,
        "clkin1_buffer_mode": None,
        "oscin_buffer_mode": None,
        "gpi_controls_str": "",
        "gpo_controls_str": "",
        "sync_pin_mode": None,
        "high_perf_mode_dist_enable": False,
        "channels": [
            {
                "id": 2,
                "name": "DEV_REFCLK",
                "divider": 12,
                "freq_str": "250 MHz",
                "driver_mode": 2,
                "coarse_digital_delay": None,
                "startup_mode_dynamic": False,
                "high_perf_mode_disable": False,
                "is_sysref": False,
            }
        ],
        "raw_channels": None,
    }
    out = NodeBuilder()._render("hmc7044.tmpl", ctx)
    assert "adi,divider = <12>; // 250 MHz" in out
    assert 'adi,extended-name = "DEV_REFCLK"' in out
    assert "hmc7044_c2: channel@2" in out
    assert "jesd204-sysref-provider;" in out


def test_hmc7044_template_sysref_channel_emits_sysref_flag():
    ctx = {
        "label": "hmc7044",
        "cs": 0,
        "spi_max_hz": 1000000,
        "pll1_clkin_frequencies": [122880000, 0, 0, 0],
        "vcxo_hz": 122880000,
        "pll2_output_hz": 3_000_000_000,
        "clock_output_names": [f"hmc7044_out{i}" for i in range(14)],
        "jesd204_sysref_provider": True,
        "jesd204_max_sysref_hz": 2000000,
        "pll1_loop_bandwidth_hz": 200,
        "pll1_ref_prio_ctrl": "0xE1",
        "pll1_ref_autorevert": True,
        "pll1_charge_pump_ua": 720,
        "pfd1_max_freq_hz": 1000000,
        "sysref_timer_divider": 1024,
        "pulse_generator_mode": 0,
        "clkin0_buffer_mode": "0x07",
        "clkin1_buffer_mode": "0x07",
        "oscin_buffer_mode": "0x15",
        "gpi_controls_str": "0x00 0x00 0x00 0x11",
        "gpo_controls_str": "0x1F 0x2B 0x00 0x00",
        "sync_pin_mode": None,
        "high_perf_mode_dist_enable": False,
        "channels": [
            {
                "id": 3,
                "name": "DEV_SYSREF",
                "divider": 3840,
                "freq_str": "781.25 kHz",
                "driver_mode": 2,
                "coarse_digital_delay": None,
                "startup_mode_dynamic": True,
                "high_perf_mode_disable": True,
                "is_sysref": True,
            }
        ],
        "raw_channels": None,
    }
    out = NodeBuilder()._render("hmc7044.tmpl", ctx)
    assert "adi,jesd204-sysref-chan;" in out
    assert "adi,startup-mode-dynamic-enable;" in out
    assert "adi,high-performance-mode-disable;" in out
    assert "adi,pll1-ref-prio-ctrl = <0xE1>;" in out
    assert "adi,pll1-ref-autorevert-enable;" in out
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py::test_hmc7044_template_renders_channel_with_freq_comment -v
```

Expected: `TemplateNotFound: hmc7044.tmpl`

- [ ] **Step 3: Create `adidt/templates/xsa/hmc7044.tmpl`**

```
		{{ label }}: hmc7044@{{ cs }} {
			compatible = "adi,hmc7044";
			#address-cells = <1>;
			#size-cells = <0>;
			#clock-cells = <1>;
			reg = <{{ cs }}>;
			spi-max-frequency = <{{ spi_max_hz }}>;
			adi,pll1-clkin-frequencies = <{{ pll1_clkin_frequencies | join(' ') }}>;
{%- if pll1_ref_prio_ctrl is not none %}
			adi,pll1-ref-prio-ctrl = <{{ pll1_ref_prio_ctrl }}>;
{%- endif %}
{%- if pll1_ref_autorevert %}
			adi,pll1-ref-autorevert-enable;
{%- endif %}
			adi,vcxo-frequency = <{{ vcxo_hz }}>;
{%- if pll1_loop_bandwidth_hz is not none %}
			adi,pll1-loop-bandwidth-hz = <{{ pll1_loop_bandwidth_hz }}>;
{%- endif %}
{%- if pll1_charge_pump_ua is not none %}
			adi,pll1-charge-pump-current-ua = <{{ pll1_charge_pump_ua }}>;
{%- endif %}
{%- if pfd1_max_freq_hz is not none %}
			adi,pfd1-maximum-limit-frequency-hz = <{{ pfd1_max_freq_hz }}>;
{%- endif %}
			adi,pll2-output-frequency = <{{ pll2_output_hz }}>;
{%- if sysref_timer_divider is not none %}
			adi,sysref-timer-divider = <{{ sysref_timer_divider }}>;
{%- endif %}
{%- if pulse_generator_mode is not none %}
			adi,pulse-generator-mode = <{{ pulse_generator_mode }}>;
{%- endif %}
{%- if clkin0_buffer_mode is not none %}
			adi,clkin0-buffer-mode = <{{ clkin0_buffer_mode }}>;
{%- endif %}
{%- if clkin1_buffer_mode is not none %}
			adi,clkin1-buffer-mode = <{{ clkin1_buffer_mode }}>;
{%- endif %}
{%- if oscin_buffer_mode is not none %}
			adi,oscin-buffer-mode = <{{ oscin_buffer_mode }}>;
{%- endif %}
{%- if gpi_controls_str %}
			adi,gpi-controls = <{{ gpi_controls_str }}>;
{%- endif %}
{%- if gpo_controls_str %}
			adi,gpo-controls = <{{ gpo_controls_str }}>;
{%- endif %}
			clock-output-names = {{ clock_output_names | map('tojson') | join(', ') }};
			jesd204-device;
			#jesd204-cells = <2>;
{%- if jesd204_sysref_provider %}
			jesd204-sysref-provider;
			adi,jesd204-max-sysref-frequency-hz = <{{ jesd204_max_sysref_hz }}>;
{%- endif %}
{%- if channels is not none %}
{%- for ch in channels %}
			{{ label }}_c{{ ch.id }}: channel@{{ ch.id }} {
				reg = <{{ ch.id }}>;
				adi,extended-name = "{{ ch.name }}";
				adi,divider = <{{ ch.divider }}>; // {{ ch.freq_str }}
				adi,driver-mode = <{{ ch.driver_mode }}>;
{%- if ch.coarse_digital_delay is not none %}
				adi,coarse-digital-delay = <{{ ch.coarse_digital_delay }}>;
{%- endif %}
{%- if ch.startup_mode_dynamic %}
				adi,startup-mode-dynamic-enable;
{%- endif %}
{%- if ch.high_perf_mode_disable %}
				adi,high-performance-mode-disable;
{%- endif %}
{%- if ch.is_sysref %}
				adi,jesd204-sysref-chan;
{%- endif %}
			};
{%- endfor %}
{%- else %}
{{ raw_channels }}
{%- endif %}
		};
```

Note: `clock_output_names | map('tojson')` produces quoted strings. If Jinja2's `tojson` filter isn't available in the environment, pre-format `clock_output_names_str` as a Python string in the context builder (e.g. `'"name0", "name1", ...'`) and use `{{ clock_output_names_str }}` directly.

> **Context boundary:** The template consumes `gpi_controls_str` and `gpo_controls_str` (pre-formatted hex strings, e.g. `"0x00 0x00 0x00 0x11"`). The `_build_hmc7044_ctx` builder accepts `gpi_controls: list | None` and `gpo_controls: list | None` as its inputs and calls `_fmt_gpi_gpo()` internally. When writing template tests directly, pass `gpi_controls_str`/`gpo_controls_str` (the formatted strings), not the raw list keys.

- [ ] **Step 4: Add `_build_hmc7044_ctx` and `_build_hmc7044_channel_ctx` to `NodeBuilder`**

Add to `adidt/xsa/node_builder.py`:

```python
@staticmethod
def _fmt_gpi_gpo(controls: list) -> str:
    """Format a list of int/hex values as a space-separated hex string for DTS."""
    return " ".join(f"0x{int(v):02X}" for v in controls)

def _build_hmc7044_channel_ctx(self, pll2_hz: int, channels_spec: list[dict]) -> list[dict]:
    """Pre-compute freq_str for each HMC7044 channel using _fmt_hz."""
    result = []
    for ch in channels_spec:
        d = dict(ch)
        if "freq_str" not in d:
            d["freq_str"] = self._fmt_hz(pll2_hz // d["divider"])
        d.setdefault("coarse_digital_delay", None)
        d.setdefault("startup_mode_dynamic", False)
        d.setdefault("high_perf_mode_disable", False)
        d.setdefault("is_sysref", False)
        result.append(d)
    return result

def _build_hmc7044_ctx(
    self,
    label: str,
    cs: int,
    spi_max_hz: int,
    pll1_clkin_frequencies: list,
    vcxo_hz: int,
    pll2_output_hz: int,
    clock_output_names: list[str],
    channels: list[dict] | None,
    raw_channels: str | None = None,
    *,
    jesd204_sysref_provider: bool = True,
    jesd204_max_sysref_hz: int = 2000000,
    pll1_loop_bandwidth_hz: int | None = None,
    pll1_ref_prio_ctrl: str | None = None,
    pll1_ref_autorevert: bool = False,
    pll1_charge_pump_ua: int | None = None,
    pfd1_max_freq_hz: int | None = None,
    sysref_timer_divider: int | None = None,
    pulse_generator_mode: int | None = None,
    clkin0_buffer_mode: str | None = None,
    clkin1_buffer_mode: str | None = None,
    oscin_buffer_mode: str | None = None,
    gpi_controls: list | None = None,
    gpo_controls: list | None = None,
    sync_pin_mode: int | None = None,
    high_perf_mode_dist_enable: bool = False,
) -> dict:
    """Build the context dict for hmc7044.tmpl."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "pll1_clkin_frequencies": pll1_clkin_frequencies,
        "vcxo_hz": vcxo_hz,
        "pll2_output_hz": pll2_output_hz,
        "clock_output_names": clock_output_names,
        "jesd204_sysref_provider": jesd204_sysref_provider,
        "jesd204_max_sysref_hz": jesd204_max_sysref_hz,
        "pll1_loop_bandwidth_hz": pll1_loop_bandwidth_hz,
        "pll1_ref_prio_ctrl": pll1_ref_prio_ctrl,
        "pll1_ref_autorevert": pll1_ref_autorevert,
        "pll1_charge_pump_ua": pll1_charge_pump_ua,
        "pfd1_max_freq_hz": pfd1_max_freq_hz,
        "sysref_timer_divider": sysref_timer_divider,
        "pulse_generator_mode": pulse_generator_mode,
        "clkin0_buffer_mode": clkin0_buffer_mode,
        "clkin1_buffer_mode": clkin1_buffer_mode,
        "oscin_buffer_mode": oscin_buffer_mode,
        "gpi_controls_str": self._fmt_gpi_gpo(gpi_controls) if gpi_controls else "",
        "gpo_controls_str": self._fmt_gpi_gpo(gpo_controls) if gpo_controls else "",
        "sync_pin_mode": sync_pin_mode,
        "high_perf_mode_dist_enable": high_perf_mode_dist_enable,
        "channels": channels,
        "raw_channels": raw_channels,
    }
```

- [ ] **Step 5: Run template tests**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py -k hmc7044 -v
```

Expected: both HMC7044 tests pass.

- [ ] **Step 6: Write context builder unit tests**

Create `test/xsa/test_node_builder_context_builders.py`:

```python
# test/xsa/test_node_builder_context_builders.py
from adidt.xsa.node_builder import NodeBuilder


def test_build_hmc7044_ctx_returns_required_keys():
    nb = NodeBuilder()
    ctx = nb._build_hmc7044_ctx(
        label="hmc7044",
        cs=0,
        spi_max_hz=1000000,
        pll1_clkin_frequencies=[122880000, 0, 0, 0],
        vcxo_hz=122880000,
        pll2_output_hz=3_000_000_000,
        clock_output_names=[f"hmc7044_out{i}" for i in range(14)],
        channels=[],
    )
    assert ctx["label"] == "hmc7044"
    assert ctx["pll2_output_hz"] == 3_000_000_000
    assert ctx["gpi_controls_str"] == ""
    assert ctx["channels"] == []
    assert ctx["raw_channels"] is None


def test_build_hmc7044_channel_ctx_computes_freq_str():
    nb = NodeBuilder()
    specs = [{"id": 2, "name": "DEV_REFCLK", "divider": 12, "driver_mode": 2}]
    channels = nb._build_hmc7044_channel_ctx(3_000_000_000, specs)
    assert channels[0]["freq_str"] == "250 MHz"
    assert channels[0]["coarse_digital_delay"] is None
    assert channels[0]["is_sysref"] is False


def test_fmt_gpi_gpo_formats_hex():
    nb = NodeBuilder()
    result = nb._fmt_gpi_gpo([0x00, 0x00, 0x00, 0x11])
    assert result == "0x00 0x00 0x00 0x11"
```

- [ ] **Step 7: Run context builder tests**

```bash
nox -s tests -- test/xsa/test_node_builder_context_builders.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add adidt/templates/xsa/hmc7044.tmpl adidt/xsa/node_builder.py \
    test/xsa/test_node_builder_templates.py \
    test/xsa/test_node_builder_context_builders.py
git commit -m "xsa: add hmc7044.tmpl and context builder methods"
```

---

### Task 3: `ad9172.tmpl` + `_build_ad9172_device_ctx`

**Files:**
- Create: `adidt/templates/xsa/ad9172.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`
- Modify: `test/xsa/test_node_builder_context_builders.py`

- [ ] **Step 1: Write failing test**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def test_ad9172_template_renders_device_node():
    ctx = {
        "label": "dac0_ad9172",
        "cs": 1,
        "spi_max_hz": 1000000,
        "clk_ref": "hmc7044 2",
        "dac_rate_khz": 6000000,
        "jesd_link_mode": 9,
        "dac_interpolation": 1,
        "channel_interpolation": 1,
        "clock_output_divider": 1,
        "jesd_link_ids": [0],
        "jesd204_inputs": "axi_ad9172_core 0 0",
    }
    out = NodeBuilder()._render("ad9172.tmpl", ctx)
    assert 'compatible = "adi,ad9172"' in out
    assert "dac0_ad9172: ad9172@1" in out
    assert "adi,dac-rate-khz = <6000000>;" in out
    assert "jesd204-link-ids = <0>;" in out
```

- [ ] **Step 2: Create `adidt/templates/xsa/ad9172.tmpl`**

```
		{{ label }}: ad9172@{{ cs }} {
			compatible = "adi,ad9172";
			#address-cells = <1>;
			#size-cells = <0>;
			reg = <{{ cs }}>;
			spi-max-frequency = <{{ spi_max_hz }}>;
			clocks = <&{{ clk_ref }}>;
			clock-names = "dac_clk";
			adi,dac-rate-khz = <{{ dac_rate_khz }}>;
			adi,jesd-link-mode = <{{ jesd_link_mode }}>;
			adi,jesd-subclass = <1>;
			adi,dac-interpolation = <{{ dac_interpolation }}>;
			adi,channel-interpolation = <{{ channel_interpolation }}>;
			adi,clock-output-divider = <{{ clock_output_divider }}>;
			adi,syncoutb-signal-type-lvds-enable;
			adi,scrambling = <1>;
			adi,sysref-mode = <2>;
			jesd204-device;
			#jesd204-cells = <2>;
			jesd204-top-device = <0>;
			jesd204-link-ids = <{{ jesd204_link_ids | join(' ') }}>;
			jesd204-inputs = <&{{ jesd204_inputs }}>;
		};
```

- [ ] **Step 3: Add `_build_ad9172_device_ctx` to `node_builder.py`**

```python
def _build_ad9172_device_ctx(self, ad: "_AD9172Cfg") -> dict:
    """Build context dict for ad9172.tmpl."""
    return {
        "label": "dac0_ad9172",
        "cs": ad.dac_cs,
        "spi_max_hz": ad.dac_spi_max,
        "clk_ref": "hmc7044 2",
        "dac_rate_khz": ad.ad9172_dac_rate_khz,
        "jesd_link_mode": ad.ad9172_jesd_link_mode,
        "dac_interpolation": ad.ad9172_dac_interpolation,
        "channel_interpolation": ad.ad9172_channel_interpolation,
        "clock_output_divider": ad.ad9172_clock_output_divider,
        "jesd204_link_ids": [0],
        "jesd204_inputs": f"{ad.dac_core_label} 0 {ad.dac_jesd_link_id}",
    }
```

- [ ] **Step 4: Run tests**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py::test_ad9172_template_renders_device_node -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/templates/xsa/ad9172.tmpl adidt/xsa/node_builder.py \
    test/xsa/test_node_builder_templates.py
git commit -m "xsa: add ad9172.tmpl and _build_ad9172_device_ctx"
```

---

### Task 4: Migrate `_build_ad9172_nodes`

**Files:**
- Modify: `adidt/xsa/node_builder.py`

> **This task is deferred — do nothing here.** The AD9172 full node migration requires `adxcvr.tmpl`, `jesd204_overlay.tmpl`, and `tpl_core.tmpl`, which are created in Chunk 3. Migrate `_build_ad9172_nodes` at the end of Task 10 (once all shared overlay templates exist). This placeholder exists to document that the AD9172 migration scope belongs to Chunk 2 logically but executes after Chunk 3 templates are ready.

---

## Chunk 3: Shared Overlay Templates + fmcdaq2 Migration

### Task 5: `ad9523_1.tmpl` + `_build_ad9523_1_ctx`

**Files:**
- Create: `adidt/templates/xsa/ad9523_1.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth: `_fmcdaq2_ad9523_channels_block()` in node_builder.py (lines ~1270–1331) and the fmcdaq2 SPI node block.

- [ ] **Step 1: Write failing test**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def test_ad9523_1_template_renders_channel():
    ctx = {
        "label": "clk0_ad9523",
        "cs": 0,
        "spi_max_hz": 10000000,
        "vcxo_hz": 125000000,
        "gpio_lines": [],
        "channels": [
            {"id": 4, "name": "ADC_CLK_FMC", "divider": 2, "freq_str": "500 MHz"},
        ],
    }
    out = NodeBuilder()._render("ad9523_1.tmpl", ctx)
    assert "clk0_ad9523" in out
    assert 'compatible = "adi,ad9523-1"' in out
    assert "adi,channel-divider = <2>; // 500 MHz" in out
    assert "adi,vcxo-freq" in out
    assert "ad9523_0_c4" in out  # label uses cs (0) in prefix


def test_ad9523_1_template_renders_sysref_channel():
    ctx = {
        "label": "clk0_ad9523",
        "cs": 0,
        "spi_max_hz": 10000000,
        "vcxo_hz": 125000000,
        "gpio_lines": [],
        "channels": [
            {"id": 5, "name": "ADC_SYSREF", "divider": 128, "freq_str": "7.8125 MHz"},
        ],
    }
    out = NodeBuilder()._render("ad9523_1.tmpl", ctx)
    assert "ad9523_0_c5" in out
    # no signal_source property in this template
    assert "adi,signal-source" not in out
```

- [ ] **Step 2: Create `adidt/templates/xsa/ad9523_1.tmpl`**

**CRITICAL: The template content must match the fmcdaq2 builder exactly (node_builder.py lines 355–377 and `_fmcdaq2_ad9523_channels_block()` lines 1270–1331). The correct property names and structure are:**

- Property order: `reg`, `spi-max-frequency`, `clock-output-names`, `#clock-cells`, `adi,vcxo-freq`, `adi,spi-3wire-enable`, `adi,pll1-bypass-enable`, `adi,osc-in-diff-enable`, `adi,pll2-charge-pump-current-nA = <413000>`, `adi,pll2-m1-freq = <1000000000>`, `adi,rpole2`, `adi,rzero`, `adi,cpole1`
- clock-output-names: hardcoded `"ad9523-1_out0"` through `"ad9523-1_out13"` (note: hyphens, not underscores)
- Channel label prefix: `ad9523_{{ cs }}_c{{ ch.id }}` (uses the SPI CS index)
- All channels: `adi,driver-mode = <3>; adi,divider-phase = <1>;` (hardcoded — not context variables)
- No `adi,signal-source` or `adi,jesd204-sysref-chan` in this template (not present in fmcdaq2 source)
- No `spi-cpol`, `spi-cpha`, no `jesd204-device`, no `jesd204-sysref-provider`

```
		{{ label }}: ad9523-1@{{ cs }} {
			compatible = "adi,ad9523-1";
			#address-cells = <1>;
			#size-cells = <0>;
			reg = <{{ cs }}>;
			spi-max-frequency = <{{ spi_max_hz }}>;
			clock-output-names = "ad9523-1_out0", "ad9523-1_out1", "ad9523-1_out2", "ad9523-1_out3", "ad9523-1_out4", "ad9523-1_out5", "ad9523-1_out6", "ad9523-1_out7", "ad9523-1_out8", "ad9523-1_out9", "ad9523-1_out10", "ad9523-1_out11", "ad9523-1_out12", "ad9523-1_out13";
			#clock-cells = <1>;
			adi,vcxo-freq = <{{ vcxo_hz }}>;
			adi,spi-3wire-enable;
			adi,pll1-bypass-enable;
			adi,osc-in-diff-enable;
			adi,pll2-charge-pump-current-nA = <413000>;
			adi,pll2-m1-freq = <1000000000>;
			adi,rpole2 = <0>;
			adi,rzero = <7>;
			adi,cpole1 = <2>;
{%- for gl in gpio_lines %}
			{{ gl.prop }} = <&{{ gl.controller }} {{ gl.index }} 0>;
{%- endfor %}
{%- for ch in channels %}
			ad9523_{{ cs }}_c{{ ch.id }}:channel@{{ ch.id }} {
				reg = <{{ ch.id }}>;
				adi,extended-name = "{{ ch.name }}";
				adi,driver-mode = <3>;
				adi,divider-phase = <1>;
				adi,channel-divider = <{{ ch.divider }}>; // {{ ch.freq_str }}
			};
{%- endfor %}
		};
```

- [ ] **Step 3: Add `_build_ad9523_1_ctx` to node_builder.py**

The 8 channels (all with driver_mode=3, divider_phase=1, no signal_source/is_sysref) come from `_fmcdaq2_ad9523_channels_block()` (lines 1270–1331). Channel names and dividers:

```python
def _build_ad9523_1_ctx(self, fmc: "_FMCDAQ2Cfg") -> dict:
    """Build context dict for ad9523_1.tmpl from an _FMCDAQ2Cfg."""
    _m1 = 1_000_000_000  # adi,pll2-m1-freq distribution frequency
    channels = [
        {"id": 1,  "name": "DAC_CLK",           "divider": 1,   "freq_str": self._fmt_hz(_m1 // 1)},
        {"id": 4,  "name": "ADC_CLK_FMC",        "divider": 2,   "freq_str": self._fmt_hz(_m1 // 2)},
        {"id": 5,  "name": "ADC_SYSREF",          "divider": 128, "freq_str": self._fmt_hz(_m1 // 128)},
        {"id": 6,  "name": "CLKD_ADC_SYSREF",     "divider": 128, "freq_str": self._fmt_hz(_m1 // 128)},
        {"id": 7,  "name": "CLKD_DAC_SYSREF",     "divider": 128, "freq_str": self._fmt_hz(_m1 // 128)},
        {"id": 8,  "name": "DAC_SYSREF",           "divider": 128, "freq_str": self._fmt_hz(_m1 // 128)},
        {"id": 9,  "name": "FMC_DAC_REF_CLK",     "divider": 2,   "freq_str": self._fmt_hz(_m1 // 2)},
        {"id": 13, "name": "ADC_CLK",              "divider": 1,   "freq_str": self._fmt_hz(_m1 // 1)},
    ]
    return {
        "label": "clk0_ad9523",
        "cs": fmc.clock_cs,
        "spi_max_hz": fmc.clock_spi_max,
        "vcxo_hz": fmc.clock_vcxo_hz,
        "gpio_lines": [],  # clock GPIO lines: pass from fmc if needed
        "channels": channels,
    }
```

> **Important:** Verify against `_fmcdaq2_ad9523_channels_block()` (lines 1270–1331). Channel IDs, names, and dividers must match exactly. All `driver_mode=3`, `divider_phase=1` are hardcoded in the template.

- [ ] **Step 4: Run all template tests**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add adidt/templates/xsa/ad9523_1.tmpl adidt/xsa/node_builder.py \
    test/xsa/test_node_builder_templates.py
git commit -m "xsa: add ad9523_1.tmpl and _build_ad9523_1_ctx"
```

---

### Task 6: Converter device templates (`ad9680.tmpl`, `ad9144.tmpl`)

**Files:**
- Create: `adidt/templates/xsa/ad9680.tmpl`
- Create: `adidt/templates/xsa/ad9144.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth: fmcdaq2 SPI node block in `_build_fmcdaq2_nodes` (node_builder.py lines ~330–422).

- [ ] **Step 1: Write failing tests**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def _make_ad9680_ctx():
    # fmcdaq2-style: 3 clocks (jesd_label, device_clk, sysref_clk), no spi-cpol/cpha
    return {
        "label": "adc0_ad9680",
        "cs": 2,
        "spi_max_hz": 1000000,
        "use_spi_3wire": False,  # fmcdaq2: no spi-cpol/cpha/spi-3wire
        "clks_str": "<&axi_ad9680_jesd204_rx>, <&clk0_ad9523 13>, <&clk0_ad9523 5>",
        "clk_names_str": '"jesd_adc_clk", "adc_clk", "adc_sysref"',
        "sampling_frequency_hz": 1000000000,
        "m": 2, "l": 4, "f": 1, "k": 32, "np": 16,
        "jesd204_top_device": 0,
        "jesd204_link_ids": [0],
        "jesd204_inputs": "axi_ad9680_core 0 0",
        "gpio_lines": [],
    }


def test_ad9680_template_renders_device_node():
    out = NodeBuilder()._render("ad9680.tmpl", _make_ad9680_ctx())
    assert 'compatible = "adi,ad9680"' in out
    assert "adc0_ad9680: ad9680@2" in out
    assert "adi,octets-per-frame = <1>;" in out
    assert "jesd204-top-device = <0>;" in out
    assert 'clock-names = "jesd_adc_clk", "adc_clk", "adc_sysref";' in out
    assert "spi-cpol" not in out  # fmcdaq2 has no spi-cpol


def _make_ad9144_ctx():
    return {
        "label": "dac0_ad9144",
        "cs": 1,
        "spi_max_hz": 1000000,
        "clk_ref": "clk0_ad9523 1",
        "jesd204_top_device": 1,
        "jesd204_link_ids": [0],
        # offset 1: AD9144 device node references the TPL core at link offset 1
        "jesd204_inputs": "axi_ad9144_core 1 0",
        "gpio_lines": [],
    }


def test_ad9144_template_renders_device_node():
    out = NodeBuilder()._render("ad9144.tmpl", _make_ad9144_ctx())
    assert 'compatible = "adi,ad9144"' in out
    assert "dac0_ad9144: ad9144@1" in out
    assert "jesd204-top-device = <1>;" in out
    assert "jesd204-inputs = <&axi_ad9144_core 1 0>;" in out
    assert "spi-cpol" not in out  # no spi-cpol in fmcdaq2 ad9144
    assert "adi,jesd-link-mode" not in out  # not present in fmcdaq2 ad9144
```

- [ ] **Step 2: Create `adidt/templates/xsa/ad9680.tmpl`**

**CRITICAL: Verify every property against fmcdaq2 (lines 378–404) and fmcdaq3 (lines 712–746). Key differences:**
- fmcdaq2: NO `spi-cpol`/`spi-cpha`, 3 clocks (`jesd_clk`+`device_clk`+`sysref_clk`), extra sysref properties at end
- fmcdaq3: has `spi-cpol`/`spi-cpha`/`adi,spi-3wire-enable`, 1 clock only

Use pre-formatted `clks_str`/`clk_names_str` context strings and a `use_spi_3wire` flag:

```
		{{ label }}: ad9680@{{ cs }} {
			compatible = "adi,ad9680";
			#address-cells = <1>;
			#size-cells = <0>;
			reg = <{{ cs }}>;
{%- if use_spi_3wire %}
			spi-cpol;
			spi-cpha;
{%- endif %}
			spi-max-frequency = <{{ spi_max_hz }}>;
{%- if use_spi_3wire %}
			adi,spi-3wire-enable;
{%- endif %}
			clocks = {{ clks_str }};
			clock-names = {{ clk_names_str }};
			jesd204-device;
			#jesd204-cells = <2>;
			jesd204-top-device = <{{ jesd204_top_device }}>;
			jesd204-link-ids = <{{ jesd204_link_ids | join(' ') }}>;
			jesd204-inputs = <&{{ jesd204_inputs }}>;
			adi,converters-per-device = <{{ m }}>;
			adi,lanes-per-device = <{{ l }}>;
			/* JESD204 framing: F = octets per frame per lane */
			adi,octets-per-frame = <{{ f }}>;
			/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */
			adi,frames-per-multiframe = <{{ k }}>;
			adi,converter-resolution = <14>;
			adi,bits-per-sample = <{{ np }}>;
			adi,control-bits-per-sample = <2>;
			adi,subclass = <1>;
			adi,sampling-frequency = /bits/ 64 <{{ sampling_frequency_hz }}>;
			adi,input-clock-divider-ratio = <1>;
{%- if not use_spi_3wire %}
			adi,sysref-lmfc-offset = <0>;
			adi,sysref-pos-window-skew = <0>;
			adi,sysref-neg-window-skew = <0>;
			adi,sysref-mode = <1>;
			adi,sysref-nshot-ignore-count = <0>;
{%- endif %}
{%- for g in gpio_lines %}
			{{ g.prop }} = <&{{ g.controller }} {{ g.index }} 0>;
{%- endfor %}
		};
```

> **Note:** The fmcdaq3 ad9680 has `sysref-*` properties too (lines 740–744). If the fmcdaq3 output includes them, remove the `not use_spi_3wire` guard and always emit them. Verify during Task 13.

- [ ] **Step 3: Create `adidt/templates/xsa/ad9144.tmpl`**

**CRITICAL: Verify against fmcdaq2 source (lines 405–421). The correct property set:**
- NO `spi-cpol`, `spi-cpha` (fmcdaq2 ad9144 has neither)
- NO `adi,jesd-link-mode` (not in fmcdaq2 source; present in fmcdaq3 ad9152)
- `jesd204-link-ids = <0>;` is hardcoded in source (use `<{{ jesd204_link_ids | join(' ') }}>` for template flexibility)
- `jesd204-inputs` offset is **1** (not 0) — line 417: `<&{fmc.dac_core_label} 1 {fmc.dac_jesd_link_id}>`
- `adi,subclass` and `adi,interpolation` appear **after** `jesd204-inputs`

```
		{{ label }}: ad9144@{{ cs }} {
			compatible = "adi,ad9144";
			#address-cells = <1>;
			#size-cells = <0>;
			reg = <{{ cs }}>;
			spi-max-frequency = <{{ spi_max_hz }}>;
			clocks = <&{{ clk_ref }}>;
			clock-names = "dac_clk";
			jesd204-device;
			#jesd204-cells = <2>;
			jesd204-top-device = <{{ jesd204_top_device }}>;
			jesd204-link-ids = <{{ jesd204_link_ids | join(' ') }}>;
			jesd204-inputs = <&{{ jesd204_inputs }}>;
			adi,subclass = <1>;
			adi,interpolation = <1>;
{%- for g in gpio_lines %}
			{{ g.prop }} = <&{{ g.controller }} {{ g.index }} 0>;
{%- endfor %}
		};
```

- [ ] **Step 4: Add `_build_ad9680_ctx` and `_build_ad9144_ctx` to node_builder.py**

```python
def _build_ad9680_ctx(self, fmc: "_FMCDAQ2Cfg") -> dict:
    """Build context dict for ad9680.tmpl (fmcdaq2 — 3 clocks, no spi-3wire)."""
    gpio_lines = []
    for prop, attr in [
        ("powerdown-gpios", "adc_powerdown_gpio"),
        ("fastdetect-a-gpios", "adc_fastdetect_a_gpio"),
        ("fastdetect-b-gpios", "adc_fastdetect_b_gpio"),
    ]:
        val = getattr(fmc, attr, None)
        if val is not None:
            gpio_lines.append({"prop": prop, "controller": fmc.gpio_controller, "index": int(val)})
    clks_str = (
        f"<&{fmc.adc_jesd_label}>, "
        f"<&clk0_ad9523 {fmc.adc_device_clk_idx}>, "
        f"<&clk0_ad9523 {fmc.adc_sysref_clk_idx}>"
    )
    return {
        "label": "adc0_ad9680",
        "cs": fmc.adc_cs,
        "spi_max_hz": fmc.adc_spi_max,
        "use_spi_3wire": False,
        "clks_str": clks_str,
        "clk_names_str": '"jesd_adc_clk", "adc_clk", "adc_sysref"',
        "sampling_frequency_hz": fmc.adc_sampling_frequency_hz,
        "m": fmc.rx_m, "l": fmc.rx_l, "f": fmc.rx_f, "k": fmc.rx_k,
        "np": fmc.rx_np,
        "jesd204_top_device": 0,
        "jesd204_link_ids": [fmc.adc_jesd_link_id],
        "jesd204_inputs": f"{fmc.adc_core_label} 0 {fmc.adc_jesd_link_id}",
        "gpio_lines": gpio_lines,
    }

def _build_ad9144_ctx(self, fmc: "_FMCDAQ2Cfg") -> dict:
    """Build context dict for ad9144.tmpl (fmcdaq2)."""
    gpio_lines = []
    for prop, attr in [
        ("txen-gpios", "dac_txen_gpio"),
        ("reset-gpios", "dac_reset_gpio"),
        ("irq-gpios", "dac_irq_gpio"),
    ]:
        val = getattr(fmc, attr, None)
        if val is not None:
            gpio_lines.append({"prop": prop, "controller": fmc.gpio_controller, "index": int(val)})
    return {
        "label": "dac0_ad9144",
        "cs": fmc.dac_cs,
        "spi_max_hz": fmc.dac_spi_max,
        "clk_ref": f"clk0_ad9523 {fmc.dac_device_clk_idx}",
        "jesd204_top_device": 1,
        "jesd204_link_ids": [fmc.dac_jesd_link_id],
        # offset 1: fmcdaq2 ad9144 device references TPL core at offset 1 (line 417)
        "jesd204_inputs": f"{fmc.dac_core_label} 1 {fmc.dac_jesd_link_id}",
        "gpio_lines": gpio_lines,
    }
```

- [ ] **Step 5: Run tests**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py -k "ad9680 or ad9144" -v
```

Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add adidt/templates/xsa/ad9680.tmpl adidt/templates/xsa/ad9144.tmpl \
    adidt/xsa/node_builder.py test/xsa/test_node_builder_templates.py
git commit -m "xsa: add ad9680.tmpl, ad9144.tmpl and context builders"
```

---

### Task 7: `adxcvr.tmpl` + `_build_adxcvr_ctx`

**Files:**
- Create: `adidt/templates/xsa/adxcvr.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth:
- fmcdaq2 adxcvr (2-clock, with jesd L/M/S): node_builder.py lines ~484–513
- fmcdaq3 adxcvr (1-clock, with jesd204-inputs): node_builder.py lines ~806–830
- AD9172 adxcvr (1-clock, use_lpm_enable=True): node_builder.py lines ~1057–1069

Key rules from spec:
- `use_div40=True` → 2-clock + jesd L/M/S + no jesd204-inputs (fmcdaq2)
- `use_div40=False` → 1-clock + jesd204-inputs (guarded by `{% if jesd204_inputs %}`)
- `use_lpm_enable`: True for fmcdaq2, fmcdaq3, AD9172; False for AD9081 only

- [ ] **Step 1: Write failing tests**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def test_adxcvr_template_2clk_variant():
    """fmcdaq2-style: 2 clocks, jesd L/M/S, no jesd204-inputs."""
    ctx = {
        "label": "axi_ad9680_adxcvr",
        "sys_clk_select": 0,
        "out_clk_select": 4,
        "clk_ref": "clk0_ad9523 4",
        "use_div40": True,
        "div40_clk_ref": "clk0_ad9523 4",
        "clock_output_names": ["adc_gt_clk", "rx_out_clk"],
        "use_lpm_enable": True,
        "jesd_l": 4,
        "jesd_m": 2,
        "jesd_s": 1,
        "jesd204_inputs": None,
        "is_rx": True,
    }
    out = NodeBuilder()._render("adxcvr.tmpl", ctx)
    assert 'clock-names = "conv", "div40"' in out
    assert "adi,jesd-l = <4>;" in out
    assert "adi,use-lpm-enable;" in out
    assert "jesd204-inputs" not in out


def test_adxcvr_template_1clk_variant_with_jesd204_inputs():
    """fmcdaq3-style: 1 clock, jesd204-inputs present."""
    ctx = {
        "label": "axi_ad9680_xcvr",
        "sys_clk_select": 0,
        "out_clk_select": 8,
        "clk_ref": "clk0_ad9528 4",
        "use_div40": False,
        "div40_clk_ref": None,
        "clock_output_names": ["adc_gt_clk", "rx_out_clk"],
        "use_lpm_enable": True,
        "jesd_l": None,
        "jesd_m": None,
        "jesd_s": None,
        "jesd204_inputs": "clk0_ad9528 0 0",
        "is_rx": True,
    }
    out = NodeBuilder()._render("adxcvr.tmpl", ctx)
    assert 'clock-names = "conv"' in out
    assert "jesd204-inputs = <&clk0_ad9528 0 0>;" in out
    assert "adi,jesd-l" not in out
    assert "adi,use-lpm-enable;" in out


def test_adxcvr_template_1clk_no_jesd204_inputs():
    """fmcdaq3 TX: 1 clock, no jesd204-inputs."""
    ctx = {
        "label": "axi_ad9152_xcvr",
        "sys_clk_select": 3,
        "out_clk_select": 8,
        "clk_ref": "clk0_ad9528 9",
        "use_div40": False,
        "div40_clk_ref": None,
        "clock_output_names": ["dac_gt_clk", "tx_out_clk"],
        "use_lpm_enable": True,
        "jesd_l": None,
        "jesd_m": None,
        "jesd_s": None,
        "jesd204_inputs": None,
        "is_rx": False,
    }
    out = NodeBuilder()._render("adxcvr.tmpl", ctx)
    assert "jesd204-inputs" not in out
```

- [ ] **Step 2: Create `adidt/templates/xsa/adxcvr.tmpl`**

```
	&{{ label }} {
		compatible = "adi,axi-adxcvr-1.0";
{%- if use_div40 %}
		clocks = <&{{ clk_ref }}>, <&{{ div40_clk_ref }}>;
		clock-names = "conv", "div40";
{%- else %}
		clocks = <&{{ clk_ref }}>;
		clock-names = "conv";
{%- endif %}
		#clock-cells = <1>;
		clock-output-names = {{ clock_output_names | map('tojson') | join(', ') }};
		adi,sys-clk-select = <{{ sys_clk_select }}>;
		adi,out-clk-select = <{{ out_clk_select }}>;
{%- if use_lpm_enable %}
		adi,use-lpm-enable;
{%- endif %}
{%- if use_div40 and jesd_l is not none %}
		adi,jesd-l = <{{ jesd_l }}>;
		adi,jesd-m = <{{ jesd_m }}>;
		adi,jesd-s = <{{ jesd_s }}>;
{%- endif %}
		jesd204-device;
		#jesd204-cells = <2>;
{%- if jesd204_inputs %}
		jesd204-inputs = <&{{ jesd204_inputs }}>;
{%- endif %}
	};
```

- [ ] **Step 3: Add `_build_adxcvr_ctx` to node_builder.py**

```python
def _build_adxcvr_ctx(self, fmc: "_FMCDAQ2Cfg", direction: str) -> dict:
    """Build context dict for adxcvr.tmpl from an _FMCDAQ2Cfg (fmcdaq2 — 2-clock variant)."""
    is_rx = direction == "rx"
    if is_rx:
        return {
            "label": fmc.adc_xcvr_label,
            "sys_clk_select": fmc.adc_sys_clk_select,
            "out_clk_select": fmc.adc_out_clk_select,
            "clk_ref": f"clk0_ad9523 {fmc.adc_xcvr_ref_clk_idx}",
            "use_div40": True,
            "div40_clk_ref": f"clk0_ad9523 {fmc.adc_xcvr_ref_clk_idx}",
            "clock_output_names": ["adc_gt_clk", "rx_out_clk"],
            "use_lpm_enable": True,
            "jesd_l": fmc.rx_l,
            "jesd_m": fmc.rx_m,
            "jesd_s": fmc.rx_s,
            "jesd204_inputs": None,
            "is_rx": True,
        }
    return {
        "label": fmc.dac_xcvr_label,
        "sys_clk_select": fmc.dac_sys_clk_select,
        "out_clk_select": fmc.dac_out_clk_select,
        "clk_ref": f"clk0_ad9523 {fmc.dac_xcvr_ref_clk_idx}",
        "use_div40": True,
        "div40_clk_ref": f"clk0_ad9523 {fmc.dac_xcvr_ref_clk_idx}",
        "clock_output_names": ["dac_gt_clk", "tx_out_clk"],
        "use_lpm_enable": True,
        "jesd_l": fmc.tx_l,
        "jesd_m": fmc.tx_m,
        "jesd_s": fmc.tx_s,
        "jesd204_inputs": None,
        "is_rx": False,
    }
```

> Other boards (fmcdaq3, AD9172, AD9081) build their adxcvr contexts inline inside their respective migration tasks. The `_build_adxcvr_ctx` is specialized for fmcdaq2; a more general version is added when fmcdaq3 is migrated.

- [ ] **Step 4: Run tests**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py -k adxcvr -v
```

Expected: all three adxcvr tests pass.

- [ ] **Step 5: Commit**

```bash
git add adidt/templates/xsa/adxcvr.tmpl adidt/xsa/node_builder.py \
    test/xsa/test_node_builder_templates.py
git commit -m "xsa: add adxcvr.tmpl and _build_adxcvr_ctx"
```

---

### Task 8: `jesd204_overlay.tmpl` + `_build_jesd204_overlay_ctx`

**Files:**
- Create: `adidt/templates/xsa/jesd204_overlay.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth:
- fmcdaq2 RX JESD overlay: node_builder.py lines ~452–465
- fmcdaq2 TX JESD overlay: node_builder.py lines ~466–483
- AD9172 TX JESD overlay: node_builder.py lines ~1040–1056

Key rules:
- `#clock-cells = <0>` is ALWAYS emitted
- `clock_output_name` guards only `clock-output-names`
- `converter_resolution` is present only for fmcdaq2 TX (value 14) and ADRV9009 TX (value 14)
- `converters_per_device`, `bits_per_sample`, `control_bits_per_sample` are populated by all TX callers; None for RX

- [ ] **Step 1: Write failing tests**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def _make_jesd_overlay_ctx_rx():
    return {
        "label": "axi_ad9680_jesd204_rx",
        "direction": "rx",
        "clocks": ["&zynqmp_clk 71", "&axi_ad9680_adxcvr 1", "&axi_ad9680_adxcvr 0"],
        "clock_names": ["s_axi_aclk", "device_clk", "lane_clk"],
        "clock_output_name": "jesd_adc_lane_clk",
        "f": 1, "k": 32,
        "jesd204_inputs": "axi_ad9680_adxcvr 0 0",
        "converter_resolution": None,
        "converters_per_device": None,
        "bits_per_sample": None,
        "control_bits_per_sample": None,
    }


def test_jesd204_overlay_rx_does_not_emit_tx_fields():
    out = NodeBuilder()._render("jesd204_overlay.tmpl", _make_jesd_overlay_ctx_rx())
    assert "&axi_ad9680_jesd204_rx {" in out
    assert "#clock-cells = <0>;" in out
    assert "clock-output-names" in out
    assert "converter-resolution" not in out
    assert "adi,octets-per-frame = <1>;" in out


def test_jesd204_overlay_tx_emits_tx_fields():
    ctx = {
        "label": "axi_ad9144_jesd204_tx",
        "direction": "tx",
        "clocks": ["&zynqmp_clk 71", "&axi_ad9144_adxcvr 1", "&axi_ad9144_adxcvr 0"],
        "clock_names": ["s_axi_aclk", "device_clk", "lane_clk"],
        "clock_output_name": "jesd_dac_lane_clk",
        "f": 1, "k": 32,
        "jesd204_inputs": "axi_ad9144_adxcvr 1 0",
        "converter_resolution": 14,
        "converters_per_device": 2,
        "bits_per_sample": 16,
        "control_bits_per_sample": 2,
    }
    out = NodeBuilder()._render("jesd204_overlay.tmpl", ctx)
    assert "adi,converter-resolution = <14>;" in out
    assert "adi,converters-per-device = <2>;" in out
    assert "adi,control-bits-per-sample = <2>;" in out


def test_jesd204_overlay_ad9081_omits_clock_output_names():
    ctx = {
        "label": "axi_mxfe_rx_jesd_rx_axi",
        "direction": "rx",
        "clocks": ["&zynqmp_clk 71", "&hmc7044 10", "&axi_mxfe_rx_xcvr 0"],
        "clock_names": ["s_axi_aclk", "device_clk", "lane_clk"],
        "clock_output_name": None,
        "f": 4, "k": 32,
        "jesd204_inputs": "axi_mxfe_rx_xcvr 0 2",
        "converter_resolution": None,
        "converters_per_device": None,
        "bits_per_sample": None,
        "control_bits_per_sample": None,
    }
    out = NodeBuilder()._render("jesd204_overlay.tmpl", ctx)
    assert "#clock-cells = <0>;" in out
    assert "clock-output-names" not in out
```

- [ ] **Step 2: Create `adidt/templates/xsa/jesd204_overlay.tmpl`**

```
	&{{ label }} {
		compatible = "adi,axi-jesd204-{{ direction }}-1.0";
		clocks = {{ clocks | map('prepend', '<&') | map('append', '>') | join(', ') }};
		clock-names = {{ clock_names | map('tojson') | join(', ') }};
		#clock-cells = <0>;
{%- if clock_output_name %}
		clock-output-names = "{{ clock_output_name }}";
{%- endif %}
		jesd204-device;
		#jesd204-cells = <2>;
		/* JESD204 framing: F = octets per frame per lane */
		adi,octets-per-frame = <{{ f }}>;
		/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */
		adi,frames-per-multiframe = <{{ k }}>;
{%- if converter_resolution is not none %}
		adi,converter-resolution = <{{ converter_resolution }}>;
{%- endif %}
{%- if bits_per_sample is not none %}
		adi,bits-per-sample = <{{ bits_per_sample }}>;
{%- endif %}
{%- if converters_per_device is not none %}
		adi,converters-per-device = <{{ converters_per_device }}>;
{%- endif %}
{%- if control_bits_per_sample is not none %}
		adi,control-bits-per-sample = <{{ control_bits_per_sample }}>;
{%- endif %}
		jesd204-inputs = <&{{ jesd204_inputs }}>;
	};
```

> **Note on Jinja2 filters:** The `clocks` list contains already-formatted strings like `"&zynqmp_clk 71"`. Use `clocks | join(', ')` directly and wrap in `<...>` in the template: `{{ clocks | map('format_clock') | join(', ') }}`. Alternatively, have the Python context builder pre-format the full `clocks = <...>` value as a string. The simplest approach: pass `clocks_str` as a pre-formatted string from the Python context builder (e.g. `"<&zynqmp_clk 71>, <&axi_ad9680_adxcvr 1>, <&axi_ad9680_adxcvr 0>"`), and the template just emits `clocks = {{ clocks_str }};`. Similarly for `clock_names_str`. Update the context contract and tests accordingly.

- [ ] **Step 3: Add `_build_jesd204_overlay_ctx` to node_builder.py**

```python
def _build_jesd204_overlay_ctx(self, fmc: "_FMCDAQ2Cfg", direction: str, ps_clk_label: str, ps_clk_index: int) -> dict:
    """Build context dict for jesd204_overlay.tmpl from an _FMCDAQ2Cfg."""
    is_rx = direction == "rx"
    if is_rx:
        xcvr = fmc.adc_xcvr_label
        jesd = fmc.adc_jesd_label
        link_id = fmc.adc_jesd_link_id
        f, k = fmc.rx_f, fmc.rx_k
        converter_resolution = None
        converters_per_device = None
        bits_per_sample = None
        control_bits_per_sample = None
        clock_output_name = "jesd_adc_lane_clk"
        jesd204_inputs = f"{xcvr} 0 {link_id}"
    else:
        xcvr = fmc.dac_xcvr_label
        jesd = fmc.dac_jesd_label
        link_id = fmc.dac_jesd_link_id
        f, k = fmc.tx_f, fmc.tx_k
        converter_resolution = 14
        converters_per_device = fmc.tx_m
        bits_per_sample = fmc.tx_np
        control_bits_per_sample = 2
        clock_output_name = "jesd_dac_lane_clk"
        jesd204_inputs = f"{xcvr} 1 {link_id}"
    clocks_str = f"<&{ps_clk_label} {ps_clk_index}>, <&{xcvr} 1>, <&{xcvr} 0>"
    clock_names_str = '"s_axi_aclk", "device_clk", "lane_clk"'
    return {
        "label": jesd,
        "direction": direction,
        "clocks_str": clocks_str,
        "clock_names_str": clock_names_str,
        "clock_output_name": clock_output_name,
        "f": f, "k": k,
        "jesd204_inputs": jesd204_inputs,
        "converter_resolution": converter_resolution,
        "converters_per_device": converters_per_device,
        "bits_per_sample": bits_per_sample,
        "control_bits_per_sample": control_bits_per_sample,
    }
```

Update the template to use `clocks_str` and `clock_names_str` pre-formatted strings:

```
		clocks = {{ clocks_str }};
		clock-names = {{ clock_names_str }};
```

Update test context dicts to use `clocks_str` and `clock_names_str` instead of lists.

- [ ] **Step 4: Run tests**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py -k jesd204_overlay -v
```

Expected: all three tests pass.

- [ ] **Step 5: Commit**

```bash
git add adidt/templates/xsa/jesd204_overlay.tmpl adidt/xsa/node_builder.py \
    test/xsa/test_node_builder_templates.py
git commit -m "xsa: add jesd204_overlay.tmpl and _build_jesd204_overlay_ctx"
```

---

### Task 9: `tpl_core.tmpl` + `_build_tpl_core_ctx`

**Files:**
- Create: `adidt/templates/xsa/tpl_core.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth:
- fmcdaq2 RX core: node_builder.py lines ~433–441
- fmcdaq2 TX core: node_builder.py lines ~442–451
- AD9172 core: node_builder.py lines ~1032–1039 (no DMA, pl_fifo_enable=True)
- AD9081 TX core: node_builder.py lines ~1849–1858 (extra clock, pl_fifo_enable=False)

- [ ] **Step 1: Write failing tests**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def test_tpl_core_rx_template():
    ctx = {
        "label": "axi_ad9680_core",
        "compatible": "adi,axi-ad9680-1.0",
        "direction": "rx",
        "dma_label": "axi_ad9680_dma",
        "spibus_label": "adc0_ad9680",
        "jesd_label": "axi_ad9680_jesd204_rx",
        "jesd_link_offset": 0,
        "link_id": 0,
        "pl_fifo_enable": False,
        "sampl_clk_ref": None,
        "sampl_clk_name": None,
    }
    out = NodeBuilder()._render("tpl_core.tmpl", ctx)
    assert "&axi_ad9680_core {" in out
    assert 'dma-names = "rx";' in out
    assert "spibus-connected = <&adc0_ad9680>;" in out
    assert "adi,axi-pl-fifo-enable" not in out
    assert "jesd204-inputs = <&axi_ad9680_jesd204_rx 0 0>;" in out


def test_tpl_core_tx_has_fifo_enable():
    ctx = {
        "label": "axi_ad9144_core",
        "compatible": "adi,axi-ad9144-1.0",
        "direction": "tx",
        "dma_label": "axi_ad9144_dma",
        "spibus_label": "dac0_ad9144",
        "jesd_label": "axi_ad9144_jesd204_tx",
        "jesd_link_offset": 1,
        "link_id": 0,
        "pl_fifo_enable": True,
        "sampl_clk_ref": None,
        "sampl_clk_name": None,
    }
    out = NodeBuilder()._render("tpl_core.tmpl", ctx)
    assert 'dma-names = "tx";' in out
    assert "adi,axi-pl-fifo-enable;" in out
    assert "jesd204-inputs = <&axi_ad9144_jesd204_tx 1 0>;" in out


def test_tpl_core_ad9172_no_dma():
    ctx = {
        "label": "axi_ad9172_core",
        "compatible": "adi,axi-ad9172-1.0",
        "direction": "tx",
        "dma_label": None,
        "spibus_label": "dac0_ad9172",
        "jesd_label": "axi_ad9172_jesd_tx_axi",
        "jesd_link_offset": 0,
        "link_id": 0,
        "pl_fifo_enable": True,
        "sampl_clk_ref": None,
        "sampl_clk_name": None,
    }
    out = NodeBuilder()._render("tpl_core.tmpl", ctx)
    assert "dmas" not in out
    assert "dma-names" not in out
    assert "adi,axi-pl-fifo-enable;" in out
```

- [ ] **Step 2: Create `adidt/templates/xsa/tpl_core.tmpl`**

```
	&{{ label }} {
		compatible = "{{ compatible }}";
{%- if dma_label is not none %}
		dmas = <&{{ dma_label }} 0>;
		dma-names = "{{ direction }}";
{%- endif %}
{%- if sampl_clk_ref is not none %}
		clocks = <&{{ sampl_clk_ref }}>;
		clock-names = "{{ sampl_clk_name }}";
{%- endif %}
		spibus-connected = <&{{ spibus_label }}>;
{%- if pl_fifo_enable %}
		adi,axi-pl-fifo-enable;
{%- endif %}
		jesd204-device;
		#jesd204-cells = <2>;
		jesd204-inputs = <&{{ jesd_label }} {{ jesd_link_offset }} {{ link_id }}>;
	};
```

- [ ] **Step 3: Add `_build_tpl_core_ctx` to node_builder.py**

```python
def _build_tpl_core_ctx(self, fmc: "_FMCDAQ2Cfg", direction: str) -> dict:
    """Build context dict for tpl_core.tmpl from an _FMCDAQ2Cfg."""
    is_rx = direction == "rx"
    if is_rx:
        return {
            "label": fmc.adc_core_label,
            "compatible": "adi,axi-ad9680-1.0",
            "direction": "rx",
            "dma_label": fmc.adc_dma_label,
            "spibus_label": "adc0_ad9680",
            "jesd_label": fmc.adc_jesd_label,
            "jesd_link_offset": 0,
            "link_id": fmc.adc_jesd_link_id,
            "pl_fifo_enable": False,
            "sampl_clk_ref": None,
            "sampl_clk_name": None,
        }
    return {
        "label": fmc.dac_core_label,
        "compatible": "adi,axi-ad9144-1.0",
        "direction": "tx",
        "dma_label": fmc.dac_dma_label,
        "spibus_label": "dac0_ad9144",
        "jesd_label": fmc.dac_jesd_label,
        "jesd_link_offset": 1,
        "link_id": fmc.dac_jesd_link_id,
        "pl_fifo_enable": True,
        "sampl_clk_ref": None,
        "sampl_clk_name": None,
    }
```

- [ ] **Step 4: Run tests**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py -k tpl_core -v
```

Expected: all three pass.

- [ ] **Step 5: Commit**

```bash
git add adidt/templates/xsa/tpl_core.tmpl adidt/xsa/node_builder.py \
    test/xsa/test_node_builder_templates.py
git commit -m "xsa: add tpl_core.tmpl and _build_tpl_core_ctx"
```

---

### Task 10: Migrate `_build_fmcdaq2_nodes` and `_build_ad9172_nodes`

**Files:**
- Modify: `adidt/xsa/node_builder.py`

Now that all shared templates and context builders exist, migrate both boards and run regression tests.

- [ ] **Step 1: Replace `_build_fmcdaq2_nodes` body**

Replace the entire return list in `_build_fmcdaq2_nodes` with:

```python
fmc = self._build_fmcdaq2_cfg(cfg)
ps_clk_label, ps_clk_index = ps_clk_label, ps_clk_index  # passed in
spi_children = (
    self._render("ad9523_1.tmpl", self._build_ad9523_1_ctx(fmc))
    + self._render("ad9680.tmpl", self._build_ad9680_ctx(fmc, ps_clk_label, ps_clk_index))
    + self._render("ad9144.tmpl", self._build_ad9144_ctx(fmc, ps_clk_label, ps_clk_index))
)
dma_rx = (
    f"\t&{fmc.adc_dma_label} {{\n"
    '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
    "\t\t#dma-cells = <1>;\n"
    "\t\t#clock-cells = <0>;\n"
    "\t};"
)
dma_tx = (
    f"\t&{fmc.dac_dma_label} {{\n"
    '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
    "\t\t#dma-cells = <1>;\n"
    "\t\t#clock-cells = <0>;\n"
    "\t};"
)
return [
    self._wrap_spi_bus(fmc.spi_bus, spi_children),
    dma_rx,
    dma_tx,
    self._render("tpl_core.tmpl", self._build_tpl_core_ctx(fmc, "rx")),
    self._render("tpl_core.tmpl", self._build_tpl_core_ctx(fmc, "tx")),
    self._render("jesd204_overlay.tmpl", self._build_jesd204_overlay_ctx(fmc, "rx", ps_clk_label, ps_clk_index)),
    self._render("jesd204_overlay.tmpl", self._build_jesd204_overlay_ctx(fmc, "tx", ps_clk_label, ps_clk_index)),
    self._render("adxcvr.tmpl", self._build_adxcvr_ctx(fmc, "rx")),
    self._render("adxcvr.tmpl", self._build_adxcvr_ctx(fmc, "tx")),
]
```

> **Important:** The order of nodes in the return list must exactly match the original builder's order. Check node_builder.py lines ~323–514 carefully. The DMA nodes, core nodes, JESD overlays, and XCVR nodes must appear in the same sequence.

- [ ] **Step 2: Migrate `_build_ad9172_nodes` to use templates**

Replace the return list in `_build_ad9172_nodes` with template calls. The AD9172 adxcvr uses a 1-clock context (no `_build_adxcvr_ctx` overload exists yet for this case — add an inline dict or add a helper). The HMC7044 context for AD9172:

```python
ad = self._build_ad9172_cfg(cfg, topology)
# AD9172 HMC7044 static channels
_pll2 = ad.hmc7044_out_freq_hz
channels = self._build_hmc7044_channel_ctx(_pll2, [
    {"id": 2,  "name": "DAC_CLK",    "divider": 8,   "driver_mode": 1, "is_sysref": False},
    {"id": 3,  "name": "DAC_SYSREF", "divider": 512, "driver_mode": 1, "is_sysref": True},
    {"id": 12, "name": "FPGA_CLK",   "divider": 8,   "driver_mode": 2, "is_sysref": False},
    {"id": 13, "name": "FPGA_SYSREF","divider": 512, "driver_mode": 2, "is_sysref": True},
])
hmc7044_ctx = self._build_hmc7044_ctx(
    label="hmc7044", cs=ad.clock_cs, spi_max_hz=ad.clock_spi_max,
    pll1_clkin_frequencies=[ad.hmc7044_ref_clk_hz, 0, 0, 0],
    vcxo_hz=ad.hmc7044_vcxo_hz,
    pll2_output_hz=ad.hmc7044_out_freq_hz,
    clock_output_names=[f"hmc7044_out{i}" for i in range(14)],
    channels=channels,
    pll1_loop_bandwidth_hz=200,
    sysref_timer_divider=1024,
    pulse_generator_mode=0,
    clkin0_buffer_mode="0x15",
    oscin_buffer_mode="0x15",
    gpi_controls=[0x00, 0x00, 0x00, 0x00],
    gpo_controls=[0x1F, 0x2B, 0x00, 0x00],
)
spi_children = (
    self._render("hmc7044.tmpl", hmc7044_ctx)
    + self._render("ad9172.tmpl", self._build_ad9172_device_ctx(ad))
)
adxcvr_ctx = {
    "label": ad.dac_xcvr_label,
    "sys_clk_select": 3,
    "out_clk_select": 4,
    "clk_ref": "hmc7044 12",
    "use_div40": False,
    "div40_clk_ref": None,
    "clock_output_names": ["dac_gt_clk", "tx_out_clk"],
    "use_lpm_enable": True,
    "jesd_l": None, "jesd_m": None, "jesd_s": None,
    "jesd204_inputs": "hmc7044 0 0",
    "is_rx": False,
}
jesd_overlay_ctx = {
    "label": ad.dac_jesd_label,
    "direction": "tx",
    "clocks_str": f"<&{ps_clk_label} {ps_clk_index}>, <&{ad.dac_xcvr_label} 1>, <&{ad.dac_xcvr_label} 0>",
    "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
    "clock_output_name": "jesd_dac_lane_clk",
    "f": ad.tx_f, "k": ad.tx_k,
    "jesd204_inputs": f"{ad.dac_xcvr_label} 0 {ad.dac_jesd_link_id}",
    "converter_resolution": None,
    "converters_per_device": ad.tx_m,
    "bits_per_sample": ad.tx_np,
    "control_bits_per_sample": 0,
}
tpl_ctx = {
    "label": ad.dac_core_label,
    "compatible": "adi,axi-ad9172-1.0",
    "direction": "tx",
    "dma_label": None,
    "spibus_label": "dac0_ad9172",
    "jesd_label": ad.dac_jesd_label,
    "jesd_link_offset": 0,
    "link_id": ad.dac_jesd_link_id,
    "pl_fifo_enable": True,
    "sampl_clk_ref": None,
    "sampl_clk_name": None,
}
return [
    self._wrap_spi_bus(ad.spi_bus, spi_children),
    self._render("tpl_core.tmpl", tpl_ctx),
    self._render("jesd204_overlay.tmpl", jesd_overlay_ctx),
    self._render("adxcvr.tmpl", adxcvr_ctx),
]
```

- [ ] **Step 3: Run full regression suite**

```bash
nox -s tests -- test/xsa/ -v
```

Expected: all existing tests pass, including `test_node_builder_fmcdaq3.py`, `test_node_builder_ad9172.py`, and the pipeline snapshot test.

If any test fails, compare the template output with the original f-string output character by character. Common issues: whitespace differences, missing newlines, property ordering.

- [ ] **Step 4: Commit**

```bash
git add adidt/xsa/node_builder.py
git commit -m "xsa: migrate _build_fmcdaq2_nodes and _build_ad9172_nodes to templates"
```

---

## Chunk 4: fmcdaq3 Migration

### Task 11: `ad9528.tmpl` + `_build_ad9528_ctx`

**Files:**
- Create: `adidt/templates/xsa/ad9528.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth: fmcdaq3 SPI node and `_fmcdaq3_ad9528_channels_block()` (node_builder.py lines ~619–720, ~1333–1406).

- [ ] **Step 1: Write failing test**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def test_ad9528_template_renders_pll_channel():
    ctx = {
        "label": "clk0_ad9528",
        "cs": 0,
        "spi_max_hz": 10000000,
        "vcxo_hz": 100000000,
        "clock_output_names": [f"ad9528_out{i}" for i in range(14)],
        "pll1_feedback_div_ratio": 4,
        "pll2_vco_output_div": 3,
        "pll2_charge_pump_current_ua": 1900,
        "channels": [
            {
                "id": 1,
                "name": "ADC_CLK",
                "channel_divider": 3,
                "freq_str": "411.11 MHz",
                "driver_mode": 2,
                "divider_phase": 0,
                "signal_source": 0,
                "is_sysref": False,
            }
        ],
    }
    out = NodeBuilder()._render("ad9528.tmpl", ctx)
    assert 'compatible = "adi,ad9528"' in out
    assert "clk0_ad9528" in out
    assert "adi,channel-divider = <3>;" in out
    assert "// 411.11 MHz" in out
```

- [ ] **Step 2: Create `adidt/templates/xsa/ad9528.tmpl`**

**CRITICAL: Verify every property against fmcdaq3 source (lines 668–690). The correct property set (from source):**
- `adi,spi-3wire-enable;` (line 674) — not `spi-cpol`/`spi-cpha`
- `clock-output-names` hardcoded: `"ad9528_out0"` through `"ad9528_out13"` (line 675)
- `#clock-cells = <1>;` (line 679)
- `adi,vcxo-freq = <{{ vcxo_hz }}>;` (not `adi,vcxo-frequency`)
- `adi,pll1-bypass-enable;` (line 681)
- `adi,osc-in-diff-enable;` (line 682)
- `adi,pll2-m1-frequency = <1233333333>;` (hardcoded, line 683)
- `adi,pll2-charge-pump-current-nA = <35000>;` (hardcoded, line 684)
- Channel label: `ad9528_{{ cs }}_c{{ ch.id }}` (source uses `ad9528_0_c{id}` where 0 is SPI CS)
- All channels: `driver_mode=3`, `divider_phase=0`, and `adi,signal-source` and optionally `adi,jesd204-sysref-chan`

```
		{{ label }}: ad9528@{{ cs }} {
			compatible = "adi,ad9528";
			#address-cells = <1>;
			#size-cells = <0>;
			reg = <{{ cs }}>;
			spi-max-frequency = <{{ spi_max_hz }}>;
			adi,spi-3wire-enable;
			clock-output-names = "ad9528_out0", "ad9528_out1", "ad9528_out2", "ad9528_out3", "ad9528_out4", "ad9528_out5", "ad9528_out6", "ad9528_out7", "ad9528_out8", "ad9528_out9", "ad9528_out10", "ad9528_out11", "ad9528_out12", "ad9528_out13";
			#clock-cells = <1>;
			adi,vcxo-freq = <{{ vcxo_hz }}>;
			adi,pll1-bypass-enable;
			adi,osc-in-diff-enable;
			adi,pll2-m1-frequency = <1233333333>;
			adi,pll2-charge-pump-current-nA = <35000>;
			jesd204-device;
			#jesd204-cells = <2>;
			jesd204-sysref-provider;
{%- for gl in gpio_lines %}
			{{ gl.prop }} = <&{{ gl.controller }} {{ gl.index }} 0>;
{%- endfor %}
{%- for ch in channels %}
			ad9528_{{ cs }}_c{{ ch.id }}: channel@{{ ch.id }} {
				reg = <{{ ch.id }}>;
				adi,extended-name = "{{ ch.name }}";
				adi,driver-mode = <3>;
				adi,divider-phase = <0>;
				adi,channel-divider = <{{ ch.divider }}>;
{%- if ch.freq_str %}
				// {{ ch.freq_str }}
{%- endif %}
				adi,signal-source = <{{ ch.signal_source }}>;
{%- if ch.is_sysref %}
				adi,jesd204-sysref-chan;
{%- endif %}
			};
{%- endfor %}
		};
```

> **Update the test to match:** The test context should use `vcxo_hz`, `gpio_lines=[]`, `channels` with fields `id`, `name`, `divider`, `freq_str`, `signal_source`, `is_sysref`. The test assertions should check for `adi,vcxo-freq` (not `adi,vcxo-frequency`), `ad9528_0_c1` label, `adi,pll2-m1-frequency`. Update the test written in Step 1 accordingly.

- [ ] **Step 3: Add `_build_ad9528_ctx` to node_builder.py**

Extract channel data from `_fmcdaq3_ad9528_channels_block()` (lines 1333–1406). The 8 channels (ids 2,4,5,6,7,8,9,13) all have `driver_mode=3`, `divider_phase=0`. Channels 5,6,7,8 have `signal_source=2`, `is_sysref=True`. Channels 2,4,9,13 have `signal_source=0`, `is_sysref=False`. Context schema: `label`, `cs`, `spi_max_hz`, `vcxo_hz`, `gpio_lines`, `channels`.

- [ ] **Step 4: Run tests, commit**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py -k ad9528 -v
git add adidt/templates/xsa/ad9528.tmpl adidt/xsa/node_builder.py test/xsa/test_node_builder_templates.py
git commit -m "xsa: add ad9528.tmpl and _build_ad9528_ctx"
```

---

### Task 12: `ad9152.tmpl` + `_build_ad9152_ctx`

**Files:**
- Create: `adidt/templates/xsa/ad9152.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth: fmcdaq3 SPI node (node_builder.py lines ~680–712).

- [ ] **Step 1: Write failing test, create template, add context builder, run tests, commit**

The AD9152 device node (fmcdaq3 source lines 691–710) has:
- `compatible = "adi,ad9152"`
- `spi-cpol;` and `spi-cpha;` (present — unlike ad9144)
- `adi,spi-3wire-enable;`
- `adi,jesd-link-mode = <{fmc.ad9152_jesd_link_mode}>;` (variable, unlike ad9144)
- `adi,subclass = <1>;`, `adi,interpolation = <1>;`
- `jesd204-inputs = <&{fmc.dac_core_label} 1 {fmc.dac_jesd_link_id}>;` (offset 1 — same as ad9144)
- `clock-names = "dac_clk";` (single clock, no jesd_clk)

```bash
git commit -m "xsa: add ad9152.tmpl and _build_ad9152_ctx"
```

---

### Task 13: Migrate `_build_fmcdaq3_nodes`

**Files:**
- Modify: `adidt/xsa/node_builder.py`

Replace the `_build_fmcdaq3_nodes` return list using the same pattern as Task 10. The fmcdaq3 adxcvr uses the 1-clock variant with `use_lpm_enable=True`; the RX adxcvr has `jesd204_inputs = "clk0_ad9528 0 0"` and the TX adxcvr has `jesd204_inputs = None`. The fmcdaq3 JESD TX overlay does NOT have `converter_resolution`.

- [ ] **Step 1: Replace `_build_fmcdaq3_nodes` with template calls**

Build adxcvr context dicts inline (no reuse of `_build_adxcvr_ctx` which is tuned for fmcdaq2).

For the fmcdaq3 ad9680, note the differences from fmcdaq2 (see source lines 712–746):
- `use_spi_3wire=True` (has `spi-cpol`, `spi-cpha`, `adi,spi-3wire-enable`)
- 1 clock only: `clks_str = f"<&clk0_ad9528 {fmc.adc_device_clk_idx}>"`, `clk_names_str = '"adc_clk"'`
- No fmcdaq2-style 3-clock layout
Either add a `_build_ad9680_fmcdaq3_ctx(fmc)` method or pass `use_spi_3wire`, `clks_str`, `clk_names_str` as parameters to a generalized method.

- [ ] **Step 2: Run full regression suite**

```bash
nox -s tests -- test/xsa/ -v
```

All existing tests including `test_node_builder_fmcdaq3.py` must pass.

- [ ] **Step 3: Commit**

```bash
git add adidt/xsa/node_builder.py
git commit -m "xsa: migrate _build_fmcdaq3_nodes to templates"
```

---

## Chunk 5: AD9081 Migration

### Task 14: `ad9081_mxfe.tmpl` + `_build_ad9081_mxfe_ctx`

**Files:**
- Create: `adidt/templates/xsa/ad9081_mxfe.tmpl`
- Modify: `adidt/xsa/node_builder.py`
- Modify: `test/xsa/test_node_builder_templates.py`

Ground truth: AD9081 SPI node (node_builder.py lines ~1896–2018).

- [ ] **Step 1: Write failing test**

Append to `test/xsa/test_node_builder_templates.py`:

```python
def test_ad9081_mxfe_template_renders_device_node():
    ctx = {
        "label": "trx0_ad9081",
        "cs": 0,
        "spi_max_hz": 5000000,
        "gpio_label": "gpio",
        "reset_gpio": 133,
        "sysref_req_gpio": 121,
        "rx2_enable_gpio": 135,
        "rx1_enable_gpio": 134,
        "tx2_enable_gpio": 137,
        "tx1_enable_gpio": 136,
        "dev_clk_ref": "hmc7044 2",
        "rx_core_label": "rx_mxfe_tpl_core_adc_tpl_core",
        "tx_core_label": "tx_mxfe_tpl_core_dac_tpl_core",
        "rx_link_id": 2,
        "tx_link_id": 0,
        "dac_frequency_hz": 12_000_000_000,
        "tx_cduc_interpolation": 8,
        "tx_fduc_interpolation": 6,
        "tx_converter_select": "<0x00> <0xFF>",
        "tx_lane_map": "0 1 2 3 4 5 6 7",
        "tx_link_mode": 9,
        "tx_m": 8, "tx_f": 4, "tx_k": 32, "tx_l": 4, "tx_s": 1,
        "adc_frequency_hz": 4_000_000_000,
        "rx_cddc_decimation": 4,
        "rx_fddc_decimation": 4,
        "rx_converter_select": "<0x00> <0xFF>",
        "rx_lane_map": "0 1 2 3 4 5 6 7",
        "rx_link_mode": 9,
        "rx_m": 8, "rx_f": 4, "rx_k": 32, "rx_l": 4, "rx_s": 1,
    }
    out = NodeBuilder()._render("ad9081_mxfe.tmpl", ctx)
    assert 'compatible = "adi,ad9081"' in out
    assert "trx0_ad9081: ad9081@0" in out
    assert "adi,tx-dacs" in out
    assert "adi,rx-adcs" in out
    assert "adi,dac-frequency-hz = /bits/ 64 <12000000000>;" in out
    assert "adi,adc-frequency-hz = /bits/ 64 <4000000000>;" in out
    assert "jesd204-link-ids = <2 0>;" in out
```

- [ ] **Step 2: Create `adidt/templates/xsa/ad9081_mxfe.tmpl`**

This is the most complex template. Trace node_builder.py lines 1896–2018 to build it. Key structural elements:
- Device node header (compatible, reg, spi-max-frequency, GPIOs, clocks, JESD linkage)
- `adi,tx-dacs` sub-tree (dac-frequency, main-data-paths with 4 dacs, channelizer-paths with 8 channels, jesd-links/link@0)
- `adi,rx-adcs` sub-tree (adc-frequency, main-data-paths with 4 adcs, channelizer-paths with 8 channels, jesd-links/link@0)

Template constants (not context variables):
- `#clock-cells = <1>;`
- `clock-output-names = "rx_sampl_clk", "tx_sampl_clk";`
- In jesd204-inputs: port index `0` for both rx_core and tx_core
- JESD link sub-node: `adi,converter-resolution = <16>; adi,bits-per-sample = <16>; adi,control-bits-per-sample = <0>;`

- [ ] **Step 3: Add `_build_ad9081_mxfe_ctx` to node_builder.py**

Extract all the local variables from `_build_ad9081_nodes` that relate to the device node (lines ~1695–1745) and package them into the context dict.

- [ ] **Step 4: Run tests, commit**

```bash
nox -s tests -- test/xsa/test_node_builder_templates.py::test_ad9081_mxfe_template_renders_device_node -v
git add adidt/templates/xsa/ad9081_mxfe.tmpl adidt/xsa/node_builder.py test/xsa/test_node_builder_templates.py
git commit -m "xsa: add ad9081_mxfe.tmpl and _build_ad9081_mxfe_ctx"
```

---

### Task 15: Migrate `_build_ad9081_nodes`

Replace the `_build_ad9081_nodes` body to use template calls. The HMC7044 block handles the `custom_hmc7044_blocks` override path (pass `channels=None, raw_channels=formatted_block`). The JESD overlay and XCVR nodes for AD9081 use inline context dicts (no dedicated helper method needed).

- [ ] **Step 1: Replace `_build_ad9081_nodes` with template calls**

Key invariants to verify during migration:
- AD9081 HMC7044: when `cfg` has `custom_hmc7044_blocks`, pass `channels=None, raw_channels=pre_rendered_string` to `hmc7044.tmpl`
- AD9081 JESD overlay `clock_output_name`: **None** for both RX and TX (no `clock-output-names` line emitted)
- AD9081 `use_lpm_enable`: **False** (not True)
- AD9081 TX `tpl_core.tmpl` context: `pl_fifo_enable=False` (source lines 1849–1858 have no `adi,axi-pl-fifo-enable`)

- [ ] **Step 2: Run full regression suite — `nox -s tests -- test/xsa/ -v`**
- [ ] **Step 3: Commit**

```bash
git commit -m "xsa: migrate _build_ad9081_nodes to templates"
```

---

## Chunk 6: ADRV9009 Migration + Cleanup

### Task 16: `ad9528_1.tmpl` + `_build_ad9528_1_ctx`

Same pattern as Task 11 (`ad9528.tmpl`) but for ADRV9009's AD9528-1. Ground truth: ADRV9009 non-FMComms8 SPI node in `_build_adrv9009_nodes`. The template is structurally identical to `ad9528.tmpl`; chip-level property names differ slightly.

- [ ] **Step 1: Write test, create `adidt/templates/xsa/ad9528_1.tmpl`, add `_build_ad9528_1_ctx(board_cfg, vcxo_hz)`, run tests, commit**

```bash
git commit -m "xsa: add ad9528_1.tmpl and _build_ad9528_1_ctx"
```

---

### Task 17: `adrv9009.tmpl` + `_build_adrv9009_device_ctx`

Ground truth: ADRV9009 device node in `_build_adrv9009_nodes` (node_builder.py lines ~2310–2500 approx). Check the actual line range by searching for `trx0_adrv9009`.

- [ ] **Step 1: Write test, create `adidt/templates/xsa/adrv9009.tmpl`, add `_build_adrv9009_device_ctx`, run tests, commit**

```bash
git commit -m "xsa: add adrv9009.tmpl and _build_adrv9009_device_ctx"
```

---

### Task 18: Migrate `_build_adrv9009_nodes`

The ADRV9009 builder is the largest and handles both standard and FMComms8 layouts. The FMComms8 path uses `hmc7044.tmpl` with `raw_channels` override.

- [ ] **Step 1: Replace `_build_adrv9009_nodes` with template calls**

Key invariants to verify during migration:
- ADRV9009 JESD overlay `clock_output_name`: **None** for both RX and TX (no `clock-output-names` line emitted)
- ADRV9009 TX JESD overlay `converter_resolution`: **14** (source line 2603 emits `adi,converter-resolution = <14>`)
- FMComms8 path: uses `hmc7044.tmpl` with `channels=None, raw_channels=default_clock_chip_channels_block` (pre-rendered string)
- Standard path: uses `ad9528_1.tmpl` for the clock chip

- [ ] **Step 2: Run full regression suite**

```bash
nox -s tests -- test/xsa/ -v
```

All tests must pass, including any ADRV9009-specific tests.

- [ ] **Step 3: Commit**

```bash
git commit -m "xsa: migrate _build_adrv9009_nodes to templates"
```

---

### Task 19: Cleanup — remove dead methods

**Files:**
- Modify: `adidt/xsa/node_builder.py`

- [ ] **Step 1: Delete dead code**

Methods to delete:
- `_fmcdaq2_ad9523_channels_block` (now replaced by `_build_ad9523_1_ctx` + template)
- `_fmcdaq3_ad9528_channels_block` (now replaced by `_build_ad9528_ctx` + template)

Local variables to remove from migrated builders:
- In `_build_ad9081_nodes`: the `default_hmc7044_channels_block` string variable (now uses `raw_channels` context)
- In `_build_adrv9009_nodes`: the `default_clock_chip_channels_block` string variable (actual variable name in source — verify at `grep "default_clock_chip_channels_block" adidt/xsa/node_builder.py`)

- [ ] **Step 2: Run full test suite one final time**

```bash
nox -s tests -- test/xsa/ -v
```

- [ ] **Step 3: Final commit**

```bash
git add adidt/xsa/node_builder.py
git commit -m "xsa: remove dead channel-block helper methods after template migration"
```
