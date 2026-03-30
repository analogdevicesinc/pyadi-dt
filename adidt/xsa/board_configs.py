"""Public board configuration dataclasses for the XSA-to-DeviceTree pipeline.

These types formalize the raw ``dict[str, Any]`` configuration that the pipeline
has historically accepted.  Each board family has a dedicated dataclass with
typed fields and defaults matching the existing ``.get(key, default)`` patterns
in :mod:`adidt.xsa.node_builder`.

Backward compatibility
~~~~~~~~~~~~~~~~~~~~~~

Every config type provides a ``from_dict`` class method so that JSON profiles,
MCP server requests, and existing test dicts continue to work unchanged::

    cfg = FMCDAQ2BoardConfig.from_dict(raw_dict)

Validation
~~~~~~~~~~

``__post_init__`` on each type runs the same checks that ``profiles.py``
``_validate_typed_keys`` previously performed (non-negative ints, non-empty
strings).  Construct the object to validate; catch ``ValueError`` on failure.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


@dataclass
class JesdLinkParams:
    """JESD204 framing parameters for one direction (RX or TX)."""

    F: int = 1
    K: int = 32
    M: int = 2
    L: int = 4
    Np: int = 16
    S: int = 1

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JesdLinkParams":
        """Construct from a dict, coercing values to int."""
        return cls(**{f.name: int(d[f.name]) for f in fields(cls) if f.name in d})


@dataclass
class JesdConfig:
    """JESD204 configuration for RX and TX directions."""

    rx: JesdLinkParams = field(default_factory=JesdLinkParams)
    tx: JesdLinkParams = field(default_factory=JesdLinkParams)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JesdConfig":
        """Construct from a ``{"rx": {...}, "tx": {...}}`` dict."""
        rx = JesdLinkParams.from_dict(d.get("rx", {}))
        tx = JesdLinkParams.from_dict(d.get("tx", {}))
        return cls(rx=rx, tx=tx)


@dataclass
class ClockConfig:
    """Clock routing configuration shared across board families."""

    rx_device_clk_label: str = "clkgen"
    rx_device_clk_index: int = 0
    tx_device_clk_label: str = "clkgen"
    tx_device_clk_index: int = 0
    rx_b_device_clk_index: Optional[int] = None
    tx_b_device_clk_index: Optional[int] = None
    # HMC7044 channel mapping (used by AD9081 profiles)
    hmc7044_rx_channel: Optional[int] = None
    hmc7044_tx_channel: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClockConfig":
        """Construct from a clock config dict, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_non_negative_int(value: int, name: str) -> None:
    """Raise ValueError if *value* is not a non-negative integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name}: expected integer, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name}: must be >= 0, got {value}")


def _validate_non_empty_str(value: str, name: str) -> None:
    """Raise ValueError if *value* is not a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: expected non-empty string")


def _board_from_dict(cls: type, d: dict[str, Any], strict: bool = False) -> Any:
    """Construct a board config dataclass from a dict.

    Unknown keys are silently ignored unless *strict* is True.
    Missing keys use field defaults.
    """
    known = {f.name for f in fields(cls)}
    if strict:
        unknown = sorted(set(d) - known)
        if unknown:
            raise ValueError(
                f"{cls.__name__}: unknown key(s): {', '.join(unknown)}"
            )
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name in d:
            val = d[f.name]
            # Coerce int fields (but not Optional/Any/list fields)
            if f.type == "int" and val is not None:
                val = int(val)
            kwargs[f.name] = val
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# FMCDAQ2
# ---------------------------------------------------------------------------


@dataclass
class FMCDAQ2BoardConfig:
    """Board-level configuration for FMCDAQ2 designs (AD9523-1 + AD9680 + AD9144).

    Example::

        cfg = FMCDAQ2BoardConfig.from_dict({
            "spi_bus": "spi0",
            "clock_cs": 0,
            "adc_cs": 2,
            "dac_cs": 1,
        })
    """

    spi_bus: str = "spi0"
    clock_cs: int = 0
    adc_cs: int = 2
    dac_cs: int = 1
    clock_vcxo_hz: int = 125_000_000
    clock_spi_max_frequency: int = 10_000_000
    adc_spi_max_frequency: int = 1_000_000
    dac_spi_max_frequency: int = 1_000_000
    adc_dma_label: str = "axi_ad9680_dma"
    dac_dma_label: str = "axi_ad9144_dma"
    adc_core_label: str = "axi_ad9680_core"
    dac_core_label: str = "axi_ad9144_core"
    adc_xcvr_label: str = "axi_ad9680_adxcvr"
    dac_xcvr_label: str = "axi_ad9144_adxcvr"
    adc_jesd_label: str = "axi_ad9680_jesd204_rx"
    dac_jesd_label: str = "axi_ad9144_jesd204_tx"
    adc_jesd_link_id: int = 0
    dac_jesd_link_id: int = 0
    gpio_controller: str = "gpio0"
    adc_device_clk_idx: int = 13
    adc_sysref_clk_idx: int = 5
    adc_xcvr_ref_clk_idx: int = 4
    adc_sampling_frequency_hz: int = 1_000_000_000
    dac_device_clk_idx: int = 1
    dac_xcvr_ref_clk_idx: int = 9
    clk_sync_gpio: Any = None
    clk_status0_gpio: Any = None
    clk_status1_gpio: Any = None
    dac_txen_gpio: Any = None
    dac_reset_gpio: Any = None
    dac_irq_gpio: Any = None
    adc_powerdown_gpio: Any = None
    adc_fastdetect_a_gpio: Any = None
    adc_fastdetect_b_gpio: Any = None

    def __post_init__(self) -> None:
        _validate_non_empty_str(self.spi_bus, "spi_bus")
        for f in fields(self):
            if f.type == "int":
                _validate_non_negative_int(getattr(self, f.name), f.name)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FMCDAQ2BoardConfig":
        """Construct from a board config dict, ignoring unknown keys."""
        return _board_from_dict(cls, d)


# ---------------------------------------------------------------------------
# FMCDAQ3
# ---------------------------------------------------------------------------


@dataclass
class FMCDAQ3BoardConfig:
    """Board-level configuration for FMCDAQ3 designs (AD9528 + AD9680 + AD9152)."""

    spi_bus: str = "spi0"
    clock_cs: int = 0
    adc_cs: int = 2
    dac_cs: int = 1
    clock_vcxo_hz: int = 100_000_000
    clock_spi_max_frequency: int = 10_000_000
    adc_spi_max_frequency: int = 10_000_000
    dac_spi_max_frequency: int = 10_000_000
    adc_dma_label: str = "axi_ad9680_dma"
    dac_dma_label: str = "axi_ad9152_dma"
    adc_core_label: str = "axi_ad9680_tpl_core_adc_tpl_core"
    dac_core_label: str = "axi_ad9152_tpl_core_dac_tpl_core"
    adc_xcvr_label: str = "axi_ad9680_xcvr"
    dac_xcvr_label: str = "axi_ad9152_xcvr"
    adc_jesd_label: str = "axi_ad9680_jesd_rx_axi"
    dac_jesd_label: str = "axi_ad9152_jesd_tx_axi"
    adc_jesd_link_id: int = 0
    dac_jesd_link_id: int = 0
    gpio_controller: str = "gpio"
    adc_device_clk_idx: int = 13
    adc_xcvr_ref_clk_idx: int = 9
    adc_sampling_frequency_hz: int = 1_233_333_333
    dac_device_clk_idx: int = 2
    dac_xcvr_ref_clk_idx: int = 4
    clk_status0_gpio: Any = None
    clk_status1_gpio: Any = None
    dac_txen_gpio: Any = None
    dac_irq_gpio: Any = None
    adc_powerdown_gpio: Any = None
    adc_fastdetect_a_gpio: Any = None
    adc_fastdetect_b_gpio: Any = None
    ad9152_jesd_link_mode: int = 4

    def __post_init__(self) -> None:
        _validate_non_empty_str(self.spi_bus, "spi_bus")
        for f in fields(self):
            if f.type == "int":
                _validate_non_negative_int(getattr(self, f.name), f.name)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FMCDAQ3BoardConfig":
        """Construct from a board config dict, ignoring unknown keys."""
        return _board_from_dict(cls, d)


# ---------------------------------------------------------------------------
# AD9172
# ---------------------------------------------------------------------------


@dataclass
class AD9172BoardConfig:
    """Board-level configuration for AD9172 DAC designs (HMC7044 + AD9172)."""

    spi_bus: str = "spi0"
    clock_cs: int = 0
    dac_cs: int = 1
    clock_spi_max_frequency: int = 10_000_000
    dac_spi_max_frequency: int = 1_000_000
    dac_core_label: str = "axi_ad9172_core"
    dac_xcvr_label: str = "axi_ad9172_adxcvr"
    dac_jesd_label: str = "axi_ad9172_jesd_tx_axi"
    dac_jesd_link_id: int = 0
    hmc7044_ref_clk_hz: int = 122_880_000
    hmc7044_vcxo_hz: int = 122_880_000
    hmc7044_out_freq_hz: int = 2_949_120_000
    ad9172_dac_rate_khz: int = 11_796_480
    ad9172_jesd_link_mode: int = 4
    ad9172_dac_interpolation: int = 8
    ad9172_channel_interpolation: int = 4
    ad9172_clock_output_divider: int = 4

    def __post_init__(self) -> None:
        _validate_non_empty_str(self.spi_bus, "spi_bus")
        for f in fields(self):
            if f.type == "int":
                _validate_non_negative_int(getattr(self, f.name), f.name)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AD9172BoardConfig":
        """Construct from a board config dict, ignoring unknown keys."""
        return _board_from_dict(cls, d)


# ---------------------------------------------------------------------------
# AD9084
# ---------------------------------------------------------------------------


@dataclass
class AD9084BoardConfig:
    """Board-level configuration for AD9084 dual-link designs.

    Captures SPI bus assignments, clock chip settings, XCVR PLL selection,
    JESD204 link IDs, and lane mappings specific to AD9084 boards
    (e.g., AD9084-FMC-EBZ on VCU118).

    Example::

        cfg = AD9084BoardConfig.from_dict({
            "converter_spi": "axi_spi_2",
            "converter_cs": 0,
            "clock_spi": "axi_spi",
            "hmc7044_cs": 1,
        })
    """

    # SPI bus assignments
    converter_spi: str = "axi_spi_2"
    converter_cs: int = 0
    clock_spi: str = "axi_spi"
    hmc7044_cs: int = 1
    converter_spi_max_hz: int = 1_000_000
    hmc7044_spi_max_hz: int = 1_000_000
    # ADF4382 PLL
    adf4382_cs: Optional[int] = None
    # HMC7044 clock configuration
    pll1_clkin_frequencies: list[int] = field(
        default_factory=lambda: [125_000_000, 125_000_000, 125_000_000, 125_000_000]
    )
    vcxo_hz: int = 125_000_000
    pll2_output_hz: int = 2_500_000_000
    fpga_refclk_channel: int = 10
    # HMC7044 tuning
    pll1_loop_bandwidth_hz: int = 200
    pll1_ref_prio_ctrl: str = "0xE1"
    pll1_ref_autorevert: bool = True
    pll1_charge_pump_ua: int = 720
    pfd1_max_freq_hz: int = 1_000_000
    sysref_timer_divider: int = 1024
    pulse_generator_mode: int = 0
    clkin0_buffer_mode: str = "0x07"
    clkin1_buffer_mode: str = "0x07"
    oscin_buffer_mode: str = "0x15"
    gpi_controls: list[int] = field(default_factory=lambda: [0x00, 0x00, 0x00, 0x00])
    gpo_controls: list[int] = field(default_factory=lambda: [0x37, 0x33, 0x00, 0x00])
    jesd204_max_sysref_hz: int = 2_000_000
    hmc7044_channels: Optional[list[dict[str, Any]]] = None
    hmc7044_channel_blocks: Optional[list[Any]] = None
    # AD9084 device clock
    dev_clk_source: Optional[str] = None
    dev_clk_ref: Optional[str] = None
    dev_clk_scales: Optional[str] = None
    dev_clk_channel: int = 9
    # Device profile
    firmware_name: Optional[str] = None
    reset_gpio: Optional[int] = None
    subclass: int = 0
    side_b_separate_tpl: bool = True
    # XCVR PLL selection
    rx_sys_clk_select: int = 3
    tx_sys_clk_select: int = 3
    rx_out_clk_select: int = 4
    tx_out_clk_select: int = 4
    # JESD204 link IDs
    rx_a_link_id: int = 0
    rx_b_link_id: int = 1
    tx_a_link_id: int = 2
    tx_b_link_id: int = 3
    # Lane mappings
    jrx0_physical_lane_mapping: Optional[str] = None
    jtx0_logical_lane_mapping: Optional[str] = None
    jrx1_physical_lane_mapping: Optional[str] = None
    jtx1_logical_lane_mapping: Optional[str] = None
    # HSCI
    hsci_label: Optional[str] = None
    hsci_speed_mhz: int = 800
    hsci_auto_linkup: bool = False

    def __post_init__(self) -> None:
        _validate_non_empty_str(self.converter_spi, "converter_spi")
        _validate_non_empty_str(self.clock_spi, "clock_spi")
        _validate_non_negative_int(self.converter_cs, "converter_cs")
        _validate_non_negative_int(self.hmc7044_cs, "hmc7044_cs")
        _validate_non_negative_int(self.vcxo_hz, "vcxo_hz")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AD9084BoardConfig":
        """Construct from a board config dict, ignoring unknown keys."""
        return _board_from_dict(cls, d)


# ---------------------------------------------------------------------------
# AD9081 / MxFE
# ---------------------------------------------------------------------------


@dataclass
class AD9081BoardConfig:
    """Board-level configuration for AD9081/AD9082/AD9083 MxFE designs."""

    clock_spi: str = "spi1"
    clock_cs: int = 0
    adc_spi: str = "spi0"
    adc_cs: int = 0
    reset_gpio: Optional[int] = None
    sysref_req_gpio: Optional[int] = None
    rx1_enable_gpio: Optional[int] = None
    rx2_enable_gpio: Optional[int] = None
    tx1_enable_gpio: Optional[int] = None
    tx2_enable_gpio: Optional[int] = None
    hmc7044_channel_blocks: Optional[list[Any]] = None

    def __post_init__(self) -> None:
        _validate_non_empty_str(self.clock_spi, "clock_spi")
        _validate_non_empty_str(self.adc_spi, "adc_spi")
        _validate_non_negative_int(self.clock_cs, "clock_cs")
        _validate_non_negative_int(self.adc_cs, "adc_cs")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AD9081BoardConfig":
        """Construct from a board config dict, ignoring unknown keys."""
        return _board_from_dict(cls, d)


# ---------------------------------------------------------------------------
# ADRV9009 / ADRV9025
# ---------------------------------------------------------------------------


@dataclass
class ADRV9009BoardConfig:
    """Board-level configuration for ADRV9009/9025/9026 transceiver designs."""

    spi_bus: str = "spi0"
    clk_cs: int = 0
    trx_cs: int = 1
    misc_clk_hz: int = 0
    trx_reset_gpio: Optional[int] = None
    trx_sysref_req_gpio: Optional[int] = None
    trx_spi_max_frequency: int = 1_000_000
    ad9528_vcxo_freq: int = 122_880_000
    rx_link_id: int = 0
    rx_os_link_id: int = 1
    tx_link_id: int = 2
    tx_octets_per_frame: Optional[int] = None
    rx_os_octets_per_frame: Optional[int] = None
    trx_profile_props: Optional[list[Any]] = None
    ad9528_channel_blocks: Optional[list[Any]] = None

    def __post_init__(self) -> None:
        _validate_non_empty_str(self.spi_bus, "spi_bus")
        _validate_non_negative_int(self.clk_cs, "clk_cs")
        _validate_non_negative_int(self.trx_cs, "trx_cs")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ADRV9009BoardConfig":
        """Construct from a board config dict, ignoring unknown keys."""
        return _board_from_dict(cls, d)
