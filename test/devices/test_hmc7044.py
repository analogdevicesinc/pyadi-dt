"""Snapshot coverage for the declarative HMC7044 device model.

The device owns its DT rendering via :mod:`adidt.devices._dt_render`;
there is no Jinja2 template and no ``build_context`` helper.  These
tests assert the rendered node's content and the non-trivial escape
hatches (``clkin0_ref`` coupled property, ``raw_channels`` block).
"""

from __future__ import annotations

from adidt.devices.clocks import HMC7044, ClockChannel
from adidt.model.board_model import BoardModel, FpgaConfig
from adidt.model.renderer import BoardModelRenderer


_PLL2_HZ = 2_949_120_000
_VCXO_HZ = 122_880_000
_CHANNEL_SPECS = [
    {
        "id": 0,
        "name": "CORE_CLK_RX",
        "divider": 8,
        "driver_mode": 2,
        "is_sysref": False,
    },
    {"id": 2, "name": "DEV_REFCLK", "divider": 4, "driver_mode": 2, "is_sysref": False},
    {
        "id": 3,
        "name": "DEV_SYSREF",
        "divider": 1024,
        "driver_mode": 2,
        "is_sysref": True,
    },
    {
        "id": 13,
        "name": "FPGA_SYSREF",
        "divider": 1024,
        "driver_mode": 2,
        "is_sysref": True,
    },
]


def _device(**overrides) -> HMC7044:
    return HMC7044(
        label="hmc7044",
        spi_max_hz=1_000_000,
        pll1_clkin_frequencies=[_VCXO_HZ, 0, 0, 0],
        vcxo_hz=_VCXO_HZ,
        pll2_output_hz=_PLL2_HZ,
        channels={spec["id"]: ClockChannel(**spec) for spec in _CHANNEL_SPECS},
        jesd204_sysref_provider=True,
        pll1_loop_bandwidth_hz=200,
        pll1_ref_prio_ctrl="0xE1",
        pll1_ref_autorevert=True,
        pll1_charge_pump_ua=720,
        pfd1_max_freq_hz=1_000_000,
        sysref_timer_divider=1024,
        pulse_generator_mode=0,
        clkin0_buffer_mode="0x07",
        clkin1_buffer_mode="0x07",
        oscin_buffer_mode="0x15",
        gpi_controls=[0x00, 0x00, 0x00, 0x00],
        gpo_controls=[0x37, 0x33, 0x00, 0x00],
        **overrides,
    )


def test_render_dt_emits_header_reg_flags_and_aliased_props() -> None:
    out = _device().render_dt(cs=0)
    # Header
    assert "hmc7044: hmc7044@0 {" in out
    assert 'compatible = "adi,hmc7044";' in out
    assert "#address-cells = <1>;" in out
    assert "#size-cells = <0>;" in out
    assert "#clock-cells = <1>;" in out
    # Class-level flags always emitted
    assert "jesd204-device;" in out
    # Aliased props
    assert "reg = <0>;" in out
    assert "spi-max-frequency = <1000000>;" in out
    assert "adi,vcxo-frequency = <122880000>;" in out
    assert "adi,pll1-clkin-frequencies = <122880000 0 0 0>;" in out
    # Hex-string values pass through as cell literals
    assert "adi,pll1-ref-prio-ctrl = <0xE1>;" in out
    assert "adi,clkin0-buffer-mode = <0x07>;" in out
    # GPI/GPO controls rendered via extra_dt_lines
    assert "adi,gpi-controls = <0x00 0x00 0x00 0x00>;" in out
    assert "adi,gpo-controls = <0x37 0x33 0x00 0x00>;" in out
    # Flags emitted only when True
    assert "adi,pll1-ref-autorevert-enable;" in out
    # clock-output-names is a list[str] rendered as quoted CSV
    assert 'clock-output-names = "hmc7044_out0", "hmc7044_out1",' in out


def test_optional_props_omitted_when_none() -> None:
    dev = HMC7044(
        label="hmc7044",
        vcxo_hz=_VCXO_HZ,
        pll2_output_hz=_PLL2_HZ,
    )
    out = dev.render_dt(cs=0)
    # Unset optionals should not appear.
    assert "adi,pll1-loop-bandwidth-hz" not in out
    assert "adi,sync-pin-mode" not in out
    assert "adi,clkin0-buffer-mode" not in out
    # Defaulted flags stay consistent with the default value.
    assert "adi,pll1-ref-autorevert-enable" not in out
    # jesd204_sysref_provider defaults to True → flag emitted.
    assert "jesd204-sysref-provider;" in out


def test_channels_render_as_subnodes_ordered_by_key() -> None:
    out = _device().render_dt(cs=0)
    assert "hmc7044_c0: channel@0 {" in out
    assert "hmc7044_c2: channel@2 {" in out
    assert "hmc7044_c3: channel@3 {" in out
    assert "hmc7044_c13: channel@13 {" in out
    # Unpopulated channels are omitted.
    assert "channel@4" not in out
    assert "channel@7" not in out
    # Channel order follows ascending key.
    assert (
        out.index("channel@0")
        < out.index("channel@2")
        < out.index("channel@3")
        < out.index("channel@13")
    )
    # Per-channel aliased props.
    assert 'adi,extended-name = "DEV_SYSREF";' in out
    assert "adi,divider = <1024>;" in out
    # SYSREF flag gates on the bool.
    assert "adi,jesd204-sysref-chan;" in out


def test_clkin0_ref_emits_coupled_clocks_and_clock_names() -> None:
    dev = _device(clkin0_ref="clkin_125")
    out = dev.render_dt(cs=0)
    assert "clocks = <&clkin_125>;" in out
    assert 'clock-names = "clkin0";' in out


def test_raw_channels_replaces_subnodes() -> None:
    raw = "\t\t\traw_block@0 { reg = <0>; };"
    dev = _device(raw_channels=raw)
    out = dev.render_dt(cs=0)
    # Per-channel sub-nodes are suppressed.
    assert "channel@0" not in out
    assert "channel@3" not in out
    # Raw block is spliced in.
    assert "raw_block@0 { reg = <0>; };" in out


def test_component_model_carries_rendered_string() -> None:
    cm = _device().to_component_model(spi_bus="spi1", spi_cs=0)
    assert cm.template == ""
    assert cm.rendered is not None
    assert "hmc7044: hmc7044@0 {" in cm.rendered


def test_board_model_renderer_uses_rendered_string() -> None:
    cm = _device().to_component_model(spi_bus="spi1", spi_cs=0)
    fpga = FpgaConfig(
        platform="zcu102",
        addr_cells=2,
        ps_clk_label="zynqmp_clk",
        ps_clk_index=71,
        gpio_label="gpio",
    )
    bm = BoardModel(name="t", platform="zcu102", components=[cm], fpga_config=fpga)
    overlays = BoardModelRenderer().render(bm)
    joined = "\n".join(overlays["converters"])
    assert "&spi1 {" in joined
    assert 'compatible = "adi,hmc7044";' in joined
    assert "hmc7044_c3: channel@3 {" in joined


def test_clk_out_exposes_14_handles_with_named_aliases() -> None:
    dev = _device()
    assert len(dev.clk_out) == 14
    assert dev.clk_out[2].name == "DEV_REFCLK"
    assert dev.clk_out[3].is_sysref is True
    assert dev.clk_out[1].name is None
