"""AD9081 MxFE device model (declarative renderer)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip
from .base import ConverterDevice, ConverterSide, Jesd204Settings


# --- JESD204 mode → framing-parameter tables --------------------------------

_AD9081_RX_MODE_TABLE: dict[tuple[int, str] | int, dict[str, int]] = {
    (1, "jesd204c"): {"M": 2, "L": 1, "F": 4, "K": 32, "Np": 16, "S": 1},
    (10, "jesd204b"): {"M": 4, "L": 4, "F": 2, "K": 32, "Np": 16, "S": 1},
    (18, "jesd204c"): {"M": 4, "L": 8, "F": 1, "K": 32, "Np": 16, "S": 1},
}

_AD9081_TX_MODE_TABLE: dict[tuple[int, str] | int, dict[str, int]] = {
    (1, "jesd204c"): {"M": 2, "L": 1, "F": 4, "K": 32, "Np": 16, "S": 1},
    (9, "jesd204b"): {"M": 4, "L": 4, "F": 4, "K": 32, "Np": 16, "S": 1},
    (17, "jesd204c"): {"M": 4, "L": 8, "F": 2, "K": 32, "Np": 16, "S": 1},
}


# --- Lane-mapping / converter-select helpers -------------------------------


def ad9081_lane_map(direction: str, lanes: int, link_mode: int) -> str:
    """Return the board-specific ``adi,logical-lane-mapping`` string."""
    if direction == "tx" and link_mode in (17, 24) and lanes == 8:
        return "0 2 7 6 1 5 4 3"
    if direction == "rx" and link_mode in (18, 26) and lanes == 8:
        return "2 0 7 6 5 4 3 1"
    if direction == "tx" and link_mode == 9 and lanes == 4:
        return "0 2 7 7 1 7 7 3"
    if direction == "rx" and link_mode == 10 and lanes == 4:
        return "2 0 7 7 7 7 3 1"
    lane_count = max(1, min(lanes, 8))
    values = list(range(lane_count)) + [7] * (8 - lane_count)
    return " ".join(str(v) for v in values)


def ad9081_converter_select(direction: str, m: int, link_mode: int) -> str:
    """Return the ``adi,converter-select`` phandle list for AD9081."""
    side = "rx" if direction == "rx" else "tx"
    if direction == "rx" and link_mode == 18 and m == 4:
        return (
            f"<&ad9081_{side}_fddc_chan0 0>, <&ad9081_{side}_fddc_chan0 1>, "
            f"<&ad9081_{side}_fddc_chan1 0>, <&ad9081_{side}_fddc_chan1 1>"
        )
    if direction == "rx" and link_mode == 26 and m == 8:
        return (
            f"<&ad9081_{side}_fddc_chan0 FDDC_I>, <&ad9081_{side}_fddc_chan0 FDDC_Q>, "
            f"<&ad9081_{side}_fddc_chan1 FDDC_I>, <&ad9081_{side}_fddc_chan1 FDDC_Q>, "
            f"<&ad9081_{side}_fddc_chan4 FDDC_I>, <&ad9081_{side}_fddc_chan4 FDDC_Q>, "
            f"<&ad9081_{side}_fddc_chan5 FDDC_I>, <&ad9081_{side}_fddc_chan5 FDDC_Q>"
        )
    if direction == "tx" and link_mode == 17 and m == 4:
        return (
            f"<&ad9081_{side}_fddc_chan0 0>, <&ad9081_{side}_fddc_chan0 1>, "
            f"<&ad9081_{side}_fddc_chan1 0>, <&ad9081_{side}_fddc_chan1 1>"
        )
    if m >= 8:
        return (
            f"<&ad9081_{side}_fddc_chan0 0>, <&ad9081_{side}_fddc_chan0 1>, "
            f"<&ad9081_{side}_fddc_chan1 0>, <&ad9081_{side}_fddc_chan1 1>, "
            f"<&ad9081_{side}_fddc_chan2 0>, <&ad9081_{side}_fddc_chan2 1>, "
            f"<&ad9081_{side}_fddc_chan3 0>, <&ad9081_{side}_fddc_chan3 1>"
        )
    return ", ".join(
        f"<&ad9081_{side}_fddc_chan{i} 0>" for i in range(max(1, min(m, 8)))
    )


# --- AD9081 side sub-models ------------------------------------------------


class AD9081Adc(ConverterSide):
    """AD9081 RX (ADC) configuration."""

    MODE_TABLE: ClassVar[dict] = _AD9081_RX_MODE_TABLE

    cddc_decimation: int = 1
    fddc_decimation: int = 1
    # Optional override for the raw ADC converter clock (``adi,adc-frequency-hz``).
    # When unset, the AD9081 device computes it as
    # ``sample_rate * cddc_decimation * fddc_decimation``.
    converter_clock: int | None = None


class AD9081Dac(ConverterSide):
    """AD9081 TX (DAC) configuration."""

    MODE_TABLE: ClassVar[dict] = _AD9081_TX_MODE_TABLE

    cduc_interpolation: int = 1
    fduc_interpolation: int = 1
    converter_clock: int | None = None


# --- Pre-rendered sub-blocks for the AD9081 MxFE node ----------------------


def _tx_dacs_block(
    *,
    dac_frequency_hz: int,
    cduc_interp: int,
    fduc_interp: int,
    converter_select: str,
    lane_map: str,
    link_mode: int,
    m: int,
    f: int,
    k: int,
    l: int,
    s: int,
) -> str:
    """Return the ``adi,tx-dacs`` sub-block as a multi-line string.

    Indentation assumes this block is spliced in at ``\\t\\t\\t`` (one tab
    deeper than the parent node's header).
    """
    return f"""adi,tx-dacs {{
\t\t\t\t#size-cells = <0>;
\t\t\t\t#address-cells = <1>;
\t\t\t\tadi,dac-frequency-hz = /bits/ 64 <{dac_frequency_hz}>;
\t\t\t\tadi,main-data-paths {{
\t\t\t\t\t#address-cells = <1>;
\t\t\t\t\t#size-cells = <0>;
\t\t\t\t\tadi,interpolation = <{cduc_interp}>;
\t\t\t\t\tdac@0 {{ reg = <0>; }};
\t\t\t\t\tdac@1 {{ reg = <1>; }};
\t\t\t\t\tdac@2 {{ reg = <2>; }};
\t\t\t\t\tdac@3 {{ reg = <3>; }};
\t\t\t\t}};
\t\t\t\tadi,channelizer-paths {{
\t\t\t\t\t#address-cells = <1>;
\t\t\t\t\t#size-cells = <0>;
\t\t\t\t\tadi,interpolation = <{fduc_interp}>;
\t\t\t\t\tad9081_tx_fddc_chan0: channel@0 {{ reg = <0>; }};
\t\t\t\t\tad9081_tx_fddc_chan1: channel@1 {{ reg = <1>; }};
\t\t\t\t\tad9081_tx_fddc_chan2: channel@2 {{ reg = <2>; }};
\t\t\t\t\tad9081_tx_fddc_chan3: channel@3 {{ reg = <3>; }};
\t\t\t\t\tad9081_tx_fddc_chan4: channel@4 {{ reg = <4>; }};
\t\t\t\t\tad9081_tx_fddc_chan5: channel@5 {{ reg = <5>; }};
\t\t\t\t\tad9081_tx_fddc_chan6: channel@6 {{ reg = <6>; }};
\t\t\t\t\tad9081_tx_fddc_chan7: channel@7 {{ reg = <7>; }};
\t\t\t\t}};
{_jesd_link_block(converter_select, lane_map, link_mode, m, f, k, l, s)}
\t\t\t}};"""


def _rx_adcs_block(
    *,
    adc_frequency_hz: int,
    cddc_decim: int,
    fddc_decim: int,
    converter_select: str,
    lane_map: str,
    link_mode: int,
    m: int,
    f: int,
    k: int,
    l: int,
    s: int,
) -> str:
    """Return the ``adi,rx-adcs`` sub-block as a multi-line string."""
    return f"""adi,rx-adcs {{
\t\t\t\t#size-cells = <0>;
\t\t\t\t#address-cells = <1>;
\t\t\t\tadi,adc-frequency-hz = /bits/ 64 <{adc_frequency_hz}>;
\t\t\t\tadi,main-data-paths {{
\t\t\t\t\t#address-cells = <1>;
\t\t\t\t\t#size-cells = <0>;
\t\t\t\t\tadc@0 {{ reg = <0>; adi,decimation = <{cddc_decim}>; }};
\t\t\t\t\tadc@1 {{ reg = <1>; adi,decimation = <{cddc_decim}>; }};
\t\t\t\t\tadc@2 {{ reg = <2>; adi,decimation = <{cddc_decim}>; }};
\t\t\t\t\tadc@3 {{ reg = <3>; adi,decimation = <{cddc_decim}>; }};
\t\t\t\t}};
\t\t\t\tadi,channelizer-paths {{
\t\t\t\t\t#address-cells = <1>;
\t\t\t\t\t#size-cells = <0>;
\t\t\t\t\tad9081_rx_fddc_chan0: channel@0 {{ reg = <0>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t\tad9081_rx_fddc_chan1: channel@1 {{ reg = <1>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t\tad9081_rx_fddc_chan2: channel@2 {{ reg = <2>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t\tad9081_rx_fddc_chan3: channel@3 {{ reg = <3>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t\tad9081_rx_fddc_chan4: channel@4 {{ reg = <4>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t\tad9081_rx_fddc_chan5: channel@5 {{ reg = <5>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t\tad9081_rx_fddc_chan6: channel@6 {{ reg = <6>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t\tad9081_rx_fddc_chan7: channel@7 {{ reg = <7>; adi,decimation = <{fddc_decim}>; }};
\t\t\t\t}};
{_jesd_link_block(converter_select, lane_map, link_mode, m, f, k, l, s)}
\t\t\t}};"""


def _jesd_link_block(
    converter_select: str,
    lane_map: str,
    link_mode: int,
    m: int,
    f: int,
    k: int,
    l: int,
    s: int,
) -> str:
    """Inner ``adi,jesd-links { link@0 { ... }; };`` block, 4 tabs deep."""
    return f"""\t\t\t\tadi,jesd-links {{
\t\t\t\t\t#size-cells = <0>;
\t\t\t\t\t#address-cells = <1>;
\t\t\t\t\tlink@0 {{
\t\t\t\t\t\treg = <0>;
\t\t\t\t\t\tadi,converter-select = {converter_select};
\t\t\t\t\t\tadi,logical-lane-mapping = /bits/ 8 <{lane_map}>;
\t\t\t\t\t\tadi,link-mode = <{link_mode}>;
\t\t\t\t\t\tadi,subclass = <1>;
\t\t\t\t\t\tadi,version = <1>;
\t\t\t\t\t\tadi,dual-link = <0>;
\t\t\t\t\t\tadi,converters-per-device = <{m}>;
\t\t\t\t\t\tadi,octets-per-frame = <{f}>;
\t\t\t\t\t\tadi,frames-per-multiframe = <{k}>;
\t\t\t\t\t\tadi,converter-resolution = <16>;
\t\t\t\t\t\tadi,bits-per-sample = <16>;
\t\t\t\t\t\tadi,control-bits-per-sample = <0>;
\t\t\t\t\t\tadi,lanes-per-device = <{l}>;
\t\t\t\t\t\tadi,samples-per-converter-per-frame = <{s}>;
\t\t\t\t\t\tadi,high-density = <0>;
\t\t\t\t\t}};
\t\t\t\t}};"""


# --- Top-level AD9081 device ----------------------------------------------


class AD9081(ConverterDevice):
    """AD9081 MxFE (quad-ADC / quad-DAC) device."""

    part: ClassVar[str] = "ad9081"
    template: ClassVar[str] = ""

    compatible: ClassVar[str] = "adi,ad9081"
    dt_header: ClassVar[dict[str, Any]] = {
        "#clock-cells": 1,
        "clock-output-names": ["rx_sampl_clk", "tx_sampl_clk"],
        "#jesd204-cells": 2,
        "jesd204-top-device": 0,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str = "trx0_ad9081"
    spi_max_hz: int = Field(5_000_000, alias="spi-max-frequency")

    adc: Annotated[AD9081Adc, DtSkip()] = Field(default_factory=AD9081Adc)
    dac: Annotated[AD9081Dac, DtSkip()] = Field(default_factory=AD9081Dac)

    # GPIO indices — emit as coupled ``<alias> = <&gpio_label N 0>;`` lines
    # via ``extra_dt_lines``; the ``gpio_label`` comes from the System
    # context.
    reset_gpio: Annotated[int | None, DtSkip()] = None
    sysref_req_gpio: Annotated[int | None, DtSkip()] = None
    rx1_enable_gpio: Annotated[int | None, DtSkip()] = None
    rx2_enable_gpio: Annotated[int | None, DtSkip()] = None
    tx1_enable_gpio: Annotated[int | None, DtSkip()] = None
    tx2_enable_gpio: Annotated[int | None, DtSkip()] = None

    # ---- API --------------------------------------------------------

    def set_jesd204_mode(self, mode: int, jesd_class: str) -> None:
        """Apply *mode* + *jesd_class* to both ADC and DAC halves."""
        self.adc.set_jesd204_mode(mode, jesd_class)
        self.dac.set_jesd204_mode(mode, jesd_class)

    @property
    def jesd204_settings(self) -> dict[str, Any]:
        """Aggregate view consumed by :class:`adidt.system.System`."""
        return {"rx": self.adc.jesd204_settings, "tx": self.dac.jesd204_settings}

    def rx_lane_map(self, lanes: int | None = None) -> str:
        l = lanes if lanes is not None else self.adc.jesd204_settings.L
        return ad9081_lane_map(
            "rx", int(l or 1), int(self.adc.jesd204_settings.jesd_mode or 0)
        )

    def tx_lane_map(self, lanes: int | None = None) -> str:
        l = lanes if lanes is not None else self.dac.jesd204_settings.L
        return ad9081_lane_map(
            "tx", int(l or 1), int(self.dac.jesd204_settings.jesd_mode or 0)
        )

    def rx_converter_select(self) -> str:
        s = self.adc.jesd204_settings
        return ad9081_converter_select("rx", int(s.M or 1), int(s.jesd_mode or 0))

    def tx_converter_select(self) -> str:
        s = self.dac.jesd204_settings
        return ad9081_converter_select("tx", int(s.M or 1), int(s.jesd_mode or 0))

    # ---- Rendering --------------------------------------------------

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        ctx = context or {}
        lines: list[str] = []
        gpio_label = ctx.get("gpio_label", "gpio")

        gpio_props = [
            ("reset-gpios", self.reset_gpio),
            ("sysref-req-gpios", self.sysref_req_gpio),
            ("rx2-enable-gpios", self.rx2_enable_gpio),
            ("rx1-enable-gpios", self.rx1_enable_gpio),
            ("tx2-enable-gpios", self.tx2_enable_gpio),
            ("tx1-enable-gpios", self.tx1_enable_gpio),
        ]
        for name, value in gpio_props:
            if value is None:
                continue
            lines.append(f"{name} = <&{gpio_label} {int(value)} 0>;")

        dev_clk_ref = ctx.get("dev_clk_ref")
        if dev_clk_ref:
            lines.append(f"clocks = <&{dev_clk_ref}>;")
            lines.append('clock-names = "dev_clk";')

        rx_link_id = int(self.adc.jesd204_settings.link_id)
        tx_link_id = int(self.dac.jesd204_settings.link_id)
        lines.append(f"jesd204-link-ids = <{rx_link_id} {tx_link_id}>;")

        rx_core = ctx.get("rx_core_label")
        tx_core = ctx.get("tx_core_label")
        if rx_core and tx_core:
            lines.append(
                f"jesd204-inputs = <&{rx_core} 0 {rx_link_id}>, "
                f"<&{tx_core} 0 {tx_link_id}>;"
            )

        return lines

    def trailing_blocks(self, context: dict | None = None) -> list[str]:
        rx = self.adc.jesd204_settings
        tx = self.dac.jesd204_settings
        adc_hz = (
            int(self.adc.converter_clock)
            if self.adc.converter_clock
            else (
                int(self.adc.sample_rate)
                * int(self.adc.cddc_decimation or 1)
                * int(self.adc.fddc_decimation or 1)
            )
        )
        dac_hz = (
            int(self.dac.converter_clock)
            if self.dac.converter_clock
            else (
                int(self.dac.sample_rate)
                * int(self.dac.cduc_interpolation or 1)
                * int(self.dac.fduc_interpolation or 1)
            )
        )

        tx_block = _tx_dacs_block(
            dac_frequency_hz=dac_hz,
            cduc_interp=int(self.dac.cduc_interpolation),
            fduc_interp=int(self.dac.fduc_interpolation),
            converter_select=self.tx_converter_select(),
            lane_map=self.tx_lane_map(),
            link_mode=int(tx.jesd_mode or 0),
            m=int(tx.M),
            f=int(tx.F),
            k=int(tx.K),
            l=int(tx.L),
            s=int(tx.S),
        )
        rx_block = _rx_adcs_block(
            adc_frequency_hz=adc_hz,
            cddc_decim=int(self.adc.cddc_decimation),
            fddc_decim=int(self.adc.fddc_decimation),
            converter_select=self.rx_converter_select(),
            lane_map=self.rx_lane_map(),
            link_mode=int(rx.jesd_mode or 0),
            m=int(rx.M),
            f=int(rx.F),
            k=int(rx.K),
            l=int(rx.L),
            s=int(rx.S),
        )
        return [tx_block, rx_block]

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        """Render this device as a DT node string."""
        return render_node(
            self,
            label=self.label,
            node_name=f"ad9081@{cs}",
            reg=cs,
            context=context,
        )

    def to_component_model(
        self, *, spi_bus: str, spi_cs: int, extra: dict[str, Any] | None = None
    ):
        from adidt.model.board_model import ComponentModel

        return ComponentModel(
            role=self.role,
            part=self.part,
            spi_bus=spi_bus,
            spi_cs=spi_cs,
            rendered=self.render_dt(cs=spi_cs, context=extra),
        )


__all__ = [
    "AD9081",
    "AD9081Adc",
    "AD9081Dac",
    "Jesd204Settings",
    "ad9081_lane_map",
    "ad9081_converter_select",
]
