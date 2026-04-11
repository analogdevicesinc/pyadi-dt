"""Transceiver context builders.

Provides context builders for AD9081 MxFE, AD9082, AD9083, AD9084,
and ADRV9009/9025 transceiver devices.
"""

from __future__ import annotations

from typing import Any


def build_ad9081_mxfe_ctx(
    *,
    label: str,
    cs: int,
    gpio_label: str,
    reset_gpio: int | None = None,
    sysref_req_gpio: int,
    rx2_enable_gpio: int,
    rx1_enable_gpio: int,
    tx2_enable_gpio: int,
    tx1_enable_gpio: int,
    dev_clk_ref: str,
    rx_core_label: str,
    tx_core_label: str,
    rx_link_id: int,
    tx_link_id: int,
    dac_frequency_hz: int,
    tx_cduc_interpolation: int,
    tx_fduc_interpolation: int,
    tx_converter_select: str,
    tx_lane_map: str,
    tx_link_mode: int,
    tx_m: int,
    tx_f: int,
    tx_k: int,
    tx_l: int,
    tx_s: int,
    adc_frequency_hz: int,
    rx_cddc_decimation: int,
    rx_fddc_decimation: int,
    rx_converter_select: str,
    rx_lane_map: str,
    rx_link_mode: int,
    rx_m: int,
    rx_f: int,
    rx_k: int,
    rx_l: int,
    rx_s: int,
    spi_max_hz: int = 5_000_000,
) -> dict:
    """Build context dict for ``ad9081_mxfe.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "gpio_label": gpio_label,
        "reset_gpio": reset_gpio,
        "sysref_req_gpio": sysref_req_gpio,
        "rx2_enable_gpio": rx2_enable_gpio,
        "rx1_enable_gpio": rx1_enable_gpio,
        "tx2_enable_gpio": tx2_enable_gpio,
        "tx1_enable_gpio": tx1_enable_gpio,
        "dev_clk_ref": dev_clk_ref,
        "rx_core_label": rx_core_label,
        "tx_core_label": tx_core_label,
        "rx_link_id": rx_link_id,
        "tx_link_id": tx_link_id,
        "dac_frequency_hz": dac_frequency_hz,
        "tx_cduc_interpolation": tx_cduc_interpolation,
        "tx_fduc_interpolation": tx_fduc_interpolation,
        "tx_converter_select": tx_converter_select,
        "tx_lane_map": tx_lane_map,
        "tx_link_mode": tx_link_mode,
        "tx_m": tx_m,
        "tx_f": tx_f,
        "tx_k": tx_k,
        "tx_l": tx_l,
        "tx_s": tx_s,
        "adc_frequency_hz": adc_frequency_hz,
        "rx_cddc_decimation": rx_cddc_decimation,
        "rx_fddc_decimation": rx_fddc_decimation,
        "rx_converter_select": rx_converter_select,
        "rx_lane_map": rx_lane_map,
        "rx_link_mode": rx_link_mode,
        "rx_m": rx_m,
        "rx_f": rx_f,
        "rx_k": rx_k,
        "rx_l": rx_l,
        "rx_s": rx_s,
    }


def build_adrv9009_device_ctx(
    *,
    phy_family: str,
    phy_compatible: str,
    trx_cs: int,
    spi_max_hz: int = 25_000_000,
    gpio_label: str,
    trx_reset_gpio: int,
    trx_sysref_req_gpio: int,
    trx_clocks_value: str,
    trx_clock_names_value: str,
    trx_link_ids_value: str,
    trx_inputs_value: str,
    trx_profile_props_block: str,
    is_fmcomms8: bool,
    trx2_cs: int | None = None,
    trx2_reset_gpio: int | None = None,
    trx1_clocks_value: str | None = None,
) -> dict:
    """Build context dict for ``adrv9009.tmpl``."""
    return {
        "phy_label": f"trx0_{phy_family}",
        "phy_node_name": f"{phy_family}-phy",
        "phy_compatible": phy_compatible,
        "trx_cs": trx_cs,
        "spi_max_hz": spi_max_hz,
        "gpio_label": gpio_label,
        "trx_reset_gpio": trx_reset_gpio,
        "trx_sysref_req_gpio": trx_sysref_req_gpio,
        "trx_clocks_value": trx_clocks_value,
        "trx_clock_names_value": trx_clock_names_value,
        "trx_link_ids_value": trx_link_ids_value,
        "trx_inputs_value": trx_inputs_value,
        "trx_profile_props_block": trx_profile_props_block,
        "is_fmcomms8": is_fmcomms8,
        "trx1_phy_label": f"trx1_{phy_family}" if is_fmcomms8 else None,
        "trx1_phy_compatible": phy_family,
        "trx2_cs": trx2_cs,
        "trx2_reset_gpio": trx2_reset_gpio,
        "trx1_clocks_value": trx1_clocks_value,
    }


def build_ad9084_ctx(
    *,
    label: str,
    cs: int,
    spi_max_hz: int = 5_000_000,
    gpio_label: str,
    reset_gpio: int | None = None,
    dev_clk_ref: str,
    dev_clk_scales: str | None = None,
    firmware_name: str | None = None,
    subclass: int = 1,
    side_b_separate_tpl: bool = False,
    jrx0_physical_lane_mapping: str | None = None,
    jtx0_logical_lane_mapping: str | None = None,
    jrx1_physical_lane_mapping: str | None = None,
    jtx1_logical_lane_mapping: str | None = None,
    hsci_label: str | None = None,
    hsci_auto_linkup: bool = False,
    link_ids: str = "",
    jesd204_inputs: str = "",
) -> dict:
    """Build context dict for ``ad9084.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "gpio_label": gpio_label,
        "reset_gpio": reset_gpio,
        "dev_clk_ref": dev_clk_ref,
        "dev_clk_scales": dev_clk_scales,
        "firmware_name": firmware_name,
        "subclass": subclass,
        "side_b_separate_tpl": side_b_separate_tpl,
        "jrx0_physical_lane_mapping": jrx0_physical_lane_mapping,
        "jtx0_logical_lane_mapping": jtx0_logical_lane_mapping,
        "jrx1_physical_lane_mapping": jrx1_physical_lane_mapping,
        "jtx1_logical_lane_mapping": jtx1_logical_lane_mapping,
        "hsci_label": hsci_label,
        "hsci_auto_linkup": hsci_auto_linkup,
        "link_ids": link_ids,
        "jesd204_inputs": jesd204_inputs,
    }


def build_ad9082_ctx(
    *,
    cs: int = 0,
    **kwargs: Any,
) -> dict:
    """Build context dict for AD9082 (delegates to :func:`build_ad9081_mxfe_ctx`)."""
    return build_ad9081_mxfe_ctx(cs=cs, **kwargs)


def build_ad9083_ctx(
    *,
    label: str = "adc0_ad9083",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
    clk_names_str: str | None = None,
    adc_frequency_hz: int | None = None,
    jesd204_top_device: int = 0,
    jesd204_link_ids: list[int] | None = None,
    jesd204_inputs: str = "",
    octets_per_frame: int | None = None,
    frames_per_multiframe: int | None = None,
) -> dict:
    """Build context dict for ``ad9083.tmpl``."""
    if jesd204_link_ids is None:
        jesd204_link_ids = [0]
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "clk_names_str": clk_names_str,
        "adc_frequency_hz": adc_frequency_hz,
        "jesd204_top_device": jesd204_top_device,
        "jesd204_link_ids": jesd204_link_ids,
        "jesd204_inputs": jesd204_inputs,
        "octets_per_frame": octets_per_frame,
        "frames_per_multiframe": frames_per_multiframe,
    }
