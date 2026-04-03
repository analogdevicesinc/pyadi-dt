# test/xsa/test_node_builder_context_builders.py
from adidt.model.contexts import (
    build_hmc7044_ctx,
    build_hmc7044_channel_ctx,
    fmt_gpi_gpo,
)


def test_build_hmc7044_ctx_returns_required_keys():
    ctx = build_hmc7044_ctx(
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
    specs = [{"id": 2, "name": "DEV_REFCLK", "divider": 12, "driver_mode": 2}]
    channels = build_hmc7044_channel_ctx(3_000_000_000, specs)
    assert channels[0]["freq_str"] == "250 MHz"
    assert channels[0]["coarse_digital_delay"] is None
    assert channels[0]["is_sysref"] is False


def test_fmt_gpi_gpo_formats_hex():
    result = fmt_gpi_gpo([0x00, 0x00, 0x00, 0x11])
    assert result == "0x00 0x00 0x00 0x11"
