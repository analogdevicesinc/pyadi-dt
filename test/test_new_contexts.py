"""Tests for the new context builders added in Task 3."""

from __future__ import annotations

import pytest

from adidt.model.contexts import (
    # clocks
    build_ad9545_ctx,
    build_ltc6952_ctx,
    build_ltc6953_ctx,
    build_adf4371_ctx,
    build_adf4377_ctx,
    build_adf4350_ctx,
    build_adf4030_ctx,
    # converters
    build_ad9088_ctx,
    build_ad9467_ctx,
    build_ad7768_ctx,
    build_adaq8092_ctx,
    build_ad9739a_ctx,
    build_ad916x_ctx,
    # transceivers
    build_ad9082_ctx,
    build_ad9083_ctx,
    # rf_frontends
    build_admv1013_ctx,
    build_admv1014_ctx,
    build_adrf6780_ctx,
    build_adar1000_ctx,
)


# ---------------------------------------------------------------------------
# Clock context builders
# ---------------------------------------------------------------------------


class TestAd9545Ctx:
    def test_defaults(self):
        ctx = build_ad9545_ctx()
        assert ctx["label"] == "clk0_ad9545"
        assert ctx["cs"] == 0
        assert ctx["spi_max_hz"] == 10_000_000
        assert ctx["clks_str"] is None
        assert ctx["clk_names_str"] is None
        assert ctx["ref_frequency_hz"] is None
        assert ctx["freq_doubler"] is False
        assert ctx["ref_crystal"] is False

    def test_custom_values(self):
        ctx = build_ad9545_ctx(
            label="my_clk",
            cs=2,
            ref_frequency_hz=125_000_000,
            freq_doubler=True,
            ref_crystal=True,
        )
        assert ctx["label"] == "my_clk"
        assert ctx["cs"] == 2
        assert ctx["ref_frequency_hz"] == 125_000_000
        assert ctx["freq_doubler"] is True
        assert ctx["ref_crystal"] is True


class TestLtc6952Ctx:
    def test_defaults(self):
        ctx = build_ltc6952_ctx()
        assert ctx["label"] == "clk0_ltc6952"
        assert ctx["compatible_id"] == "ltc6952"
        assert ctx["channels"] == []
        assert ctx["vco_frequency_hz"] is None
        assert ctx["ref_frequency_hz"] is None

    def test_with_channels(self):
        chs = [{"id": 0, "name": "OUT0", "divider": 4}]
        ctx = build_ltc6952_ctx(channels=chs)
        assert ctx["channels"] == chs


class TestLtc6953Ctx:
    def test_defaults(self):
        ctx = build_ltc6953_ctx()
        assert ctx["label"] == "clk0_ltc6953"
        assert ctx["compatible_id"] == "ltc6953"
        assert ctx["channels"] == []

    def test_with_channels(self):
        chs = [{"id": 1, "name": "CLK1", "divider": 2}]
        ctx = build_ltc6953_ctx(channels=chs)
        assert ctx["channels"] == chs


class TestAdf4371Ctx:
    def test_defaults(self):
        ctx = build_adf4371_ctx()
        assert ctx["label"] == "pll0_adf4371"
        assert ctx["compatible_id"] == "adf4371"
        assert ctx["spi_3wire"] is False
        assert ctx["muxout_select"] is None
        assert ctx["charge_pump_microamp"] is None
        assert ctx["mute_till_lock"] is False

    def test_custom_values(self):
        ctx = build_adf4371_ctx(
            spi_3wire=True, mute_till_lock=True, charge_pump_microamp=900
        )
        assert ctx["spi_3wire"] is True
        assert ctx["mute_till_lock"] is True
        assert ctx["charge_pump_microamp"] == 900


class TestAdf4377Ctx:
    def test_defaults(self):
        ctx = build_adf4377_ctx()
        assert ctx["label"] == "pll0_adf4377"
        assert ctx["compatible_id"] == "adf4377"
        assert ctx["muxout_select"] is None

    def test_muxout(self):
        ctx = build_adf4377_ctx(muxout_select="high_z")
        assert ctx["muxout_select"] == "high_z"


class TestAdf4350Ctx:
    def test_defaults(self):
        ctx = build_adf4350_ctx()
        assert ctx["label"] == "pll0_adf4350"
        assert ctx["compatible_id"] == "adf4350"
        assert ctx["channel_spacing"] is None
        assert ctx["power_up_frequency"] is None
        assert ctx["output_power"] is None
        assert ctx["charge_pump_current"] is None
        assert ctx["muxout_select"] is None

    def test_custom_values(self):
        ctx = build_adf4350_ctx(
            channel_spacing=1000, power_up_frequency=2400_000_000, output_power=3
        )
        assert ctx["channel_spacing"] == 1000
        assert ctx["power_up_frequency"] == 2400_000_000
        assert ctx["output_power"] == 3


class TestAdf4030Ctx:
    def test_defaults(self):
        ctx = build_adf4030_ctx()
        assert ctx["label"] == "clk0_adf4030"
        assert ctx["channels"] == []
        assert ctx["vco_frequency_hz"] is None
        assert ctx["bsync_frequency_hz"] is None

    def test_with_channels(self):
        chs = [{"id": 0, "name": "SYNC0", "divider": 8}]
        ctx = build_adf4030_ctx(channels=chs, vco_frequency_hz=12_000_000_000)
        assert ctx["channels"] == chs
        assert ctx["vco_frequency_hz"] == 12_000_000_000


# ---------------------------------------------------------------------------
# Converter context builders
# ---------------------------------------------------------------------------


class TestAd9088Ctx:
    def test_defaults(self):
        ctx = build_ad9088_ctx()
        assert ctx["label"] == "adc0_ad9088"
        assert ctx["cs"] == 0
        assert ctx["spi_3wire"] is False
        assert ctx["firmware_name"] is None
        assert ctx["subclass"] is None
        assert ctx["jesd204_top_device"] == 0
        assert ctx["link_ids"] == "0"

    def test_custom(self):
        ctx = build_ad9088_ctx(firmware_name="ad9088_fw.bin", subclass=1)
        assert ctx["firmware_name"] == "ad9088_fw.bin"
        assert ctx["subclass"] == 1


class TestAd9467Ctx:
    def test_defaults(self):
        ctx = build_ad9467_ctx()
        assert ctx["label"] == "adc0_ad9467"
        assert ctx["compatible_id"] == "ad9467"
        assert ctx["reset_gpio"] is None
        assert ctx["gpio_label"] == "gpio"

    def test_with_reset(self):
        ctx = build_ad9467_ctx(reset_gpio=42)
        assert ctx["reset_gpio"] == 42


class TestAd7768Ctx:
    def test_defaults(self):
        ctx = build_ad7768_ctx()
        assert ctx["label"] == "adc0_ad7768"
        assert ctx["compatible_id"] == "ad7768"
        assert ctx["dma_label"] is None
        assert ctx["data_lines"] is None
        assert ctx["reset_gpio"] is None

    def test_custom(self):
        ctx = build_ad7768_ctx(dma_label="rx_dma", data_lines=4, reset_gpio=10)
        assert ctx["dma_label"] == "rx_dma"
        assert ctx["data_lines"] == 4
        assert ctx["reset_gpio"] == 10


class TestAdaq8092Ctx:
    def test_defaults(self):
        ctx = build_adaq8092_ctx()
        assert ctx["label"] == "adc0_adaq8092"
        assert ctx["cs"] == 0
        assert ctx["spi_max_hz"] == 10_000_000
        assert ctx["clks_str"] is None


class TestAd9739aCtx:
    def test_defaults(self):
        ctx = build_ad9739a_ctx()
        assert ctx["label"] == "dac0_ad9739a"
        assert ctx["full_scale_microamp"] is None
        assert ctx["reset_gpio"] is None
        assert ctx["gpio_label"] == "gpio"

    def test_custom(self):
        ctx = build_ad9739a_ctx(full_scale_microamp=20000, reset_gpio=5)
        assert ctx["full_scale_microamp"] == 20000
        assert ctx["reset_gpio"] == 5


class TestAd916xCtx:
    def test_defaults(self):
        ctx = build_ad916x_ctx()
        assert ctx["label"] == "dac0_ad916x"
        assert ctx["compatible_id"] == "ad9162"
        assert ctx["jesd204_link_ids"] == [0]
        assert ctx["interpolation"] is None
        assert ctx["subclass"] is None

    def test_custom(self):
        ctx = build_ad916x_ctx(
            compatible_id="ad9163",
            interpolation=8,
            jesd204_link_ids=[0, 1],
            subclass=1,
        )
        assert ctx["compatible_id"] == "ad9163"
        assert ctx["interpolation"] == 8
        assert ctx["jesd204_link_ids"] == [0, 1]
        assert ctx["subclass"] == 1


# ---------------------------------------------------------------------------
# Transceiver context builders
# ---------------------------------------------------------------------------


class TestAd9082Ctx:
    def test_delegates_to_ad9081(self):
        """AD9082 ctx builder delegates to build_ad9081_mxfe_ctx."""
        ctx = build_ad9082_ctx(
            cs=1,
            label="mxfe0",
            gpio_label="gpio0",
            sysref_req_gpio=5,
            rx2_enable_gpio=6,
            rx1_enable_gpio=7,
            tx2_enable_gpio=8,
            tx1_enable_gpio=9,
            dev_clk_ref="clk 0",
            rx_core_label="rx_tpl",
            tx_core_label="tx_tpl",
            rx_link_id=0,
            tx_link_id=1,
            dac_frequency_hz=12_000_000_000,
            tx_cduc_interpolation=12,
            tx_fduc_interpolation=4,
            tx_converter_select="0xAB",
            tx_lane_map="0x01234567",
            tx_link_mode=9,
            tx_m=8,
            tx_f=2,
            tx_k=32,
            tx_l=4,
            tx_s=1,
            adc_frequency_hz=4_000_000_000,
            rx_cddc_decimation=4,
            rx_fddc_decimation=4,
            rx_converter_select="0xFF",
            rx_lane_map="0x76543210",
            rx_link_mode=10,
            rx_m=8,
            rx_f=2,
            rx_k=32,
            rx_l=4,
            rx_s=1,
        )
        assert ctx["cs"] == 1
        assert ctx["label"] == "mxfe0"
        assert ctx["dac_frequency_hz"] == 12_000_000_000


class TestAd9083Ctx:
    def test_defaults(self):
        ctx = build_ad9083_ctx()
        assert ctx["label"] == "adc0_ad9083"
        assert ctx["cs"] == 0
        assert ctx["jesd204_link_ids"] == [0]
        assert ctx["adc_frequency_hz"] is None
        assert ctx["octets_per_frame"] is None
        assert ctx["frames_per_multiframe"] is None

    def test_custom(self):
        ctx = build_ad9083_ctx(adc_frequency_hz=2_000_000_000, jesd204_link_ids=[0, 1])
        assert ctx["adc_frequency_hz"] == 2_000_000_000
        assert ctx["jesd204_link_ids"] == [0, 1]


# ---------------------------------------------------------------------------
# RF front-end context builders
# ---------------------------------------------------------------------------


class TestAdmv1013Ctx:
    def test_defaults(self):
        ctx = build_admv1013_ctx()
        assert ctx["label"] == "admv1013_0"
        assert ctx["spi_max_hz"] == 1_000_000
        assert ctx["input_mode"] is None
        assert ctx["quad_se_mode"] is None
        assert ctx["detector_enable"] is False

    def test_custom(self):
        ctx = build_admv1013_ctx(input_mode="iq", detector_enable=True)
        assert ctx["input_mode"] == "iq"
        assert ctx["detector_enable"] is True


class TestAdmv1014Ctx:
    def test_defaults(self):
        ctx = build_admv1014_ctx()
        assert ctx["label"] == "admv1014_0"
        assert ctx["spi_max_hz"] == 1_000_000
        assert ctx["clks_str"] is None


class TestAdrf6780Ctx:
    def test_defaults(self):
        ctx = build_adrf6780_ctx()
        assert ctx["label"] == "adrf6780_0"
        assert ctx["spi_max_hz"] == 1_000_000
        assert ctx["clks_str"] is None


class TestAdar1000Ctx:
    def test_defaults(self):
        ctx = build_adar1000_ctx()
        assert ctx["label"] == "adar1000_0"
        assert ctx["spi_max_hz"] == 10_000_000
        assert ctx["clks_str"] is None
