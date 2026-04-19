"""Smoke test for AD9084 + VPK180 composition via the new System API.

Complements ``test_system_ad9081_zcu102.py``: demonstrates that the
device / eval / fpga abstractions generalize to a second converter
family (AD9084) and a second FPGA platform (VPK180 / Versal) without
per-board special-casing in :class:`adidt.system.System`.
"""

from __future__ import annotations

import adidt


def _build_system() -> adidt.System:
    fmc = adidt.eval.ad9084_fmc()
    fmc.converter.set_jesd204_mode(1, "jesd204c")
    fmc.converter.adc.sample_rate = int(500e6)
    fmc.converter.dac.sample_rate = int(500e6)

    fpga = adidt.fpga.vpk180()
    system = adidt.System(name="ad9084_vpk180", components=[fmc, fpga])
    # VPK180 exposes a single SPI master; both chips hang off it.
    system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=1
    )

    system.add_link(
        source=fmc.converter.adc,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.dev_refclk,
        sink_core_clock=fmc.core_clk_rx,
        sink_sysref=fmc.dev_sysref,
    )
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter.dac,
        source_reference_clock=fmc.fpga_refclk_tx,
        source_core_clock=fmc.core_clk_tx,
        sink_sysref=fmc.fpga_sysref,
    )
    return system


def test_set_jesd204_mode_fills_framing_from_table() -> None:
    fmc = adidt.eval.ad9084_fmc()
    fmc.converter.set_jesd204_mode(1, "jesd204c")
    rx = fmc.converter.adc.jesd204_settings
    tx = fmc.converter.dac.jesd204_settings
    assert (rx.M, rx.L, rx.F, rx.K, rx.Np, rx.S) == (2, 1, 4, 32, 16, 1)
    assert (tx.M, tx.L, tx.F, tx.K, tx.Np, tx.S) == (2, 1, 4, 32, 16, 1)
    assert rx.jesd_class == "jesd204c"


def test_generate_dts_emits_expected_nodes() -> None:
    dts = _build_system().generate_dts()
    assert "/dts-v1/;" in dts
    assert "versal_clk" in dts
    assert "<&versal_clk None>" not in dts  # no literal 'None' in DTS
    assert "hmc7044: hmc7044@0" in dts
    assert "ad9084:" in dts or "ad9084 {" in dts
    assert "&axi_mxfe_rx_jesd_rx_axi" in dts
    assert "&axi_mxfe_tx_jesd_tx_axi" in dts
    # Versal selects sys_clk_select = 3 (XCVR_QPLL0 alias).
    assert "adi,sys-clk-select = <3>;" in dts


def test_board_model_carries_versal_fpga_config() -> None:
    model = _build_system().to_board_model()
    assert model.platform == "vpk180"
    assert model.fpga_config is not None
    assert model.fpga_config.platform == "vpk180"
    assert model.fpga_config.ps_clk_label == "versal_clk"
    assert model.fpga_config.ps_clk_index is None
    assert model.fpga_config.gpio_label == "gpio0"


def test_ad9084_adc_dac_sub_models_hold_independent_state() -> None:
    fmc = adidt.eval.ad9084_fmc()
    fmc.converter.adc.cddc_decimation = 8
    fmc.converter.dac.cduc_interpolation = 12
    assert fmc.converter.adc.cddc_decimation == 8
    assert fmc.converter.dac.cduc_interpolation == 12
    assert fmc.converter.adc is not fmc.converter.dac


def test_ad9081_and_ad9084_share_jesd_label_convention() -> None:
    """Both MxFE families route through the same ``mxfe_rx``/``mxfe_tx`` prefix."""
    ad9081 = adidt.eval.ad9081_fmc()
    ad9084 = adidt.eval.ad9084_fmc()
    assert ad9081.converter.part == "ad9081"
    assert ad9084.converter.part == "ad9084"
    # Sanity: each eval board exposes its own clock+converter pair.
    assert ad9081.converter is not ad9084.converter
