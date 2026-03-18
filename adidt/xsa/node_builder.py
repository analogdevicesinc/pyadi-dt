# adidt/xsa/node_builder.py
"""Build ADI device-driver DTS overlay nodes from an XSA topology and config."""
import os
import warnings
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .topology import XsaTopology, Jesd204Instance, ClkgenInstance, ConverterInstance


@dataclass
class _FMCDAQ2Cfg:
    spi_bus: str
    clock_cs: int
    adc_cs: int
    dac_cs: int
    clock_vcxo_hz: int
    clock_spi_max: int
    adc_spi_max: int
    dac_spi_max: int
    adc_dma_label: str
    dac_dma_label: str
    adc_core_label: str
    dac_core_label: str
    adc_xcvr_label: str
    dac_xcvr_label: str
    adc_jesd_label: str
    dac_jesd_label: str
    adc_jesd_link_id: int
    dac_jesd_link_id: int
    gpio_controller: str
    adc_device_clk_idx: int
    adc_sysref_clk_idx: int
    adc_xcvr_ref_clk_idx: int
    adc_sampling_frequency_hz: int
    dac_device_clk_idx: int
    dac_xcvr_ref_clk_idx: int
    clk_sync_gpio: Any
    clk_status0_gpio: Any
    clk_status1_gpio: Any
    dac_txen_gpio: Any
    dac_reset_gpio: Any
    dac_irq_gpio: Any
    adc_powerdown_gpio: Any
    adc_fastdetect_a_gpio: Any
    adc_fastdetect_b_gpio: Any
    rx_l: int
    rx_m: int
    rx_f: int
    rx_k: int
    rx_np: int
    rx_s: int
    tx_l: int
    tx_m: int
    tx_f: int
    tx_k: int
    tx_np: int
    tx_s: int
    adc_sys_clk_select: int
    dac_sys_clk_select: int
    adc_out_clk_select: int
    dac_out_clk_select: int


@dataclass
class _FMCDAQ3Cfg:
    spi_bus: str
    clock_cs: int
    adc_cs: int
    dac_cs: int
    clock_vcxo_hz: int
    clock_spi_max: int
    adc_spi_max: int
    dac_spi_max: int
    adc_dma_label: str
    dac_dma_label: str
    adc_core_label: str
    dac_core_label: str
    adc_xcvr_label: str
    dac_xcvr_label: str
    adc_jesd_label: str
    dac_jesd_label: str
    adc_jesd_link_id: int
    dac_jesd_link_id: int
    gpio_controller: str
    adc_device_clk_idx: int
    adc_xcvr_ref_clk_idx: int
    adc_sampling_frequency_hz: int
    dac_device_clk_idx: int
    dac_xcvr_ref_clk_idx: int
    clk_status0_gpio: Any
    clk_status1_gpio: Any
    dac_txen_gpio: Any
    dac_irq_gpio: Any
    adc_powerdown_gpio: Any
    adc_fastdetect_a_gpio: Any
    adc_fastdetect_b_gpio: Any
    rx_l: int
    rx_m: int
    rx_f: int
    rx_k: int
    rx_np: int
    rx_s: int
    tx_l: int
    tx_m: int
    tx_f: int
    tx_k: int
    tx_np: int
    tx_s: int
    ad9152_jesd_link_mode: int
    adc_sys_clk_select: int
    dac_sys_clk_select: int
    adc_out_clk_select: int
    dac_out_clk_select: int


@dataclass
class _AD9172Cfg:
    spi_bus: str
    clock_cs: int
    dac_cs: int
    clock_spi_max: int
    dac_spi_max: int
    dac_core_label: str
    dac_xcvr_label: str
    dac_jesd_label: str
    dac_jesd_link_id: int
    hmc7044_ref_clk_hz: int
    hmc7044_vcxo_hz: int
    hmc7044_out_freq_hz: int
    ad9172_dac_rate_khz: int
    ad9172_jesd_link_mode: int
    ad9172_dac_interpolation: int
    ad9172_channel_interpolation: int
    ad9172_clock_output_divider: int
    tx_l: int
    tx_m: int
    tx_f: int
    tx_k: int
    tx_np: int


class NodeBuilder:
    """Builds ADI DTS node strings from XsaTopology + pyadi-jif JSON config."""

    _AD9081_LINK_MODE_BY_ML: dict[tuple[int, int], tuple[int, int]] = {
        # (M, L): (rx_link_mode, tx_link_mode)
        (8, 4): (17, 18),
        (4, 8): (10, 11),
    }
    _ADRV90XX_KEYWORDS = ("adrv9009", "adrv9025", "adrv9026")

    @classmethod
    def _is_adrv90xx_name(cls, value: str) -> bool:
        """Return True if *value* contains an ADRV9009/9025/9026 keyword."""
        lower = value.lower()
        return any(key in lower for key in cls._ADRV90XX_KEYWORDS)

    def build(self, topology: XsaTopology, cfg: dict[str, Any]) -> dict[str, list[str]]:
        """Render ADI DTS nodes.

        Returns:
            Dict with keys "jesd204_rx", "jesd204_tx", "converters".
        """
        clock_map = self._build_clock_map(topology)
        ps_clk_label, ps_clk_index, gpio_label = self._platform_ps_labels(topology)
        result: dict[str, list[str]] = {
            "clkgens": [],
            "jesd204_rx": [],
            "jesd204_tx": [],
            "converters": [],
        }
        is_adrv9009_design = any(
            c.ip_type in {"axi_adrv9009", "axi_adrv9025", "axi_adrv9026"}
            or self._is_adrv90xx_name(c.name)
            for c in topology.converters
        )
        is_adrv9009_design = is_adrv9009_design or any(
            self._is_adrv90xx_name(j.name)
            for j in topology.jesd204_rx + topology.jesd204_tx
        )
        is_ad9081_mxfe_design = any(
            c.ip_type == "axi_ad9081" for c in topology.converters
        ) and any(
            "mxfe" in j.name.lower() for j in topology.jesd204_rx + topology.jesd204_tx
        )
        is_fmcdaq2_design = topology.is_fmcdaq2_design()
        is_fmcdaq3_design = topology.is_fmcdaq3_design()
        is_ad9172_design = self._is_ad9172_design(topology) or ("ad9172_board" in cfg)
        rx_labels: list[str] = []
        tx_labels: list[str] = []

        for clkgen in topology.clkgens:
            if is_adrv9009_design and self._is_adrv90xx_name(clkgen.name):
                continue
            result["clkgens"].append(
                self._render_clkgen(clkgen, ps_clk_label, ps_clk_index)
            )

        for inst in topology.jesd204_rx:
            if is_adrv9009_design and self._is_adrv90xx_name(inst.name):
                continue
            if is_ad9081_mxfe_design and "mxfe" in inst.name.lower():
                continue
            if is_fmcdaq2_design or is_fmcdaq3_design:
                continue
            clkgen_label, device_clk_label, device_clk_index = self._resolve_clock(
                inst, clock_map, cfg, "rx", ps_clk_label, ps_clk_index
            )
            jesd_input_label, jesd_input_link_id = self._resolve_jesd_input(
                inst, cfg, "rx", clkgen_label
            )
            result["jesd204_rx"].append(
                self._render_jesd(
                    inst,
                    cfg.get("jesd", {}).get("rx", {}),
                    clkgen_label,
                    device_clk_label,
                    device_clk_index,
                    jesd_input_label,
                    jesd_input_link_id,
                    ps_clk_label,
                    ps_clk_index,
                )
            )
            rx_labels.append(inst.name.replace("-", "_"))

        for inst in topology.jesd204_tx:
            if is_adrv9009_design and self._is_adrv90xx_name(inst.name):
                continue
            if is_ad9081_mxfe_design and "mxfe" in inst.name.lower():
                continue
            if is_fmcdaq2_design or is_fmcdaq3_design or is_ad9172_design:
                continue
            clkgen_label, device_clk_label, device_clk_index = self._resolve_clock(
                inst, clock_map, cfg, "tx", ps_clk_label, ps_clk_index
            )
            jesd_input_label, jesd_input_link_id = self._resolve_jesd_input(
                inst, cfg, "tx", clkgen_label
            )
            result["jesd204_tx"].append(
                self._render_jesd(
                    inst,
                    cfg.get("jesd", {}).get("tx", {}),
                    clkgen_label,
                    device_clk_label,
                    device_clk_index,
                    jesd_input_label,
                    jesd_input_link_id,
                    ps_clk_label,
                    ps_clk_index,
                )
            )
            tx_labels.append(inst.name.replace("-", "_"))

        for conv in topology.converters:
            if is_ad9081_mxfe_design and conv.ip_type == "axi_ad9081":
                continue
            if is_fmcdaq2_design and conv.ip_type in {"axi_ad9680", "axi_ad9144"}:
                continue
            if is_fmcdaq3_design and conv.ip_type in {"axi_ad9680", "axi_ad9152"}:
                continue
            if is_ad9172_design and conv.ip_type in {"axi_ad9162"}:
                continue
            rx_label = rx_labels[0] if rx_labels else "jesd_rx"
            tx_label = tx_labels[0] if tx_labels else "jesd_tx"
            result["converters"].append(
                self._render_converter(conv, rx_label, tx_label)
            )

        result["converters"].extend(
            self._build_ad9081_nodes(
                topology, cfg, ps_clk_label, ps_clk_index, gpio_label
            )
        )
        result["converters"].extend(self._build_adrv9009_nodes(topology, cfg))
        result["converters"].extend(
            self._build_fmcdaq2_nodes(topology, cfg, ps_clk_label, ps_clk_index)
        )
        result["converters"].extend(
            self._build_fmcdaq3_nodes(topology, cfg, ps_clk_label, ps_clk_index)
        )
        result["converters"].extend(
            self._build_ad9172_nodes(topology, cfg, ps_clk_label, ps_clk_index)
        )

        return result

    @staticmethod
    def _is_ad9172_design(topology: XsaTopology) -> bool:
        """Return True if the topology contains an AD9172/AD9162 DAC design."""
        if any(c.ip_type == "axi_ad9162" for c in topology.converters):
            return True
        names = " ".join(
            j.name.lower() for j in topology.jesd204_rx + topology.jesd204_tx
        )
        return "ad9172" in names or "ad9162" in names

    def _build_fmcdaq2_nodes(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> list[str]:
        """Build DTS node strings for an FMCDAQ2 (AD9523 + AD9680 + AD9144) design.

        Returns an empty list if the topology is not an FMCDAQ2 design.
        """
        if not topology.is_fmcdaq2_design():
            return []

        fmc = self._build_fmcdaq2_cfg(cfg)
        clk_gpio_lines = self._format_optional_gpio_lines(
            fmc.gpio_controller,
            [
                ("sync-gpios", fmc.clk_sync_gpio, "clk_sync_gpio"),
                ("status0-gpios", fmc.clk_status0_gpio, "clk_status0_gpio"),
                ("status1-gpios", fmc.clk_status1_gpio, "clk_status1_gpio"),
            ],
        )
        dac_gpio_lines = self._format_optional_gpio_lines(
            fmc.gpio_controller,
            [
                ("txen-gpios", fmc.dac_txen_gpio, "dac_txen_gpio"),
                ("reset-gpios", fmc.dac_reset_gpio, "dac_reset_gpio"),
                ("irq-gpios", fmc.dac_irq_gpio, "dac_irq_gpio"),
            ],
        )
        adc_gpio_lines = self._format_optional_gpio_lines(
            fmc.gpio_controller,
            [
                ("powerdown-gpios", fmc.adc_powerdown_gpio, "adc_powerdown_gpio"),
                (
                    "fastdetect-a-gpios",
                    fmc.adc_fastdetect_a_gpio,
                    "adc_fastdetect_a_gpio",
                ),
                (
                    "fastdetect-b-gpios",
                    fmc.adc_fastdetect_b_gpio,
                    "adc_fastdetect_b_gpio",
                ),
            ],
        )

        return [
            f"\t&{fmc.spi_bus} {{\n"
            '\t\tstatus = "okay";\n'
            f"\t\tclk0_ad9523: ad9523-1@{fmc.clock_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9523-1";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            f"\t\t\treg = <{fmc.clock_cs}>;\n"
            f"\t\t\tspi-max-frequency = <{fmc.clock_spi_max}>;\n"
            '\t\t\tclock-output-names = "ad9523-1_out0", "ad9523-1_out1", "ad9523-1_out2", '
            '"ad9523-1_out3", "ad9523-1_out4", "ad9523-1_out5", "ad9523-1_out6", '
            '"ad9523-1_out7", "ad9523-1_out8", "ad9523-1_out9", "ad9523-1_out10", '
            '"ad9523-1_out11", "ad9523-1_out12", "ad9523-1_out13";\n'
            "\t\t\t#clock-cells = <1>;\n"
            f"\t\t\tadi,vcxo-freq = <{fmc.clock_vcxo_hz}>;\n"
            "\t\t\tadi,spi-3wire-enable;\n"
            "\t\t\tadi,pll1-bypass-enable;\n"
            "\t\t\tadi,osc-in-diff-enable;\n"
            "\t\t\tadi,pll2-charge-pump-current-nA = <413000>;\n"
            "\t\t\tadi,pll2-m1-freq = <1000000000>;\n"
            "\t\t\tadi,rpole2 = <0>;\n"
            "\t\t\tadi,rzero = <7>;\n"
            "\t\t\tadi,cpole1 = <2>;\n"
            f"{clk_gpio_lines}"
            f"{self._fmcdaq2_ad9523_channels_block()}"
            "\t\t};\n"
            f"\t\tadc0_ad9680: ad9680@{fmc.adc_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9680";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            f"\t\t\treg = <{fmc.adc_cs}>;\n"
            f"\t\t\tspi-max-frequency = <{fmc.adc_spi_max}>;\n"
            f"\t\t\tclocks = <&{fmc.adc_jesd_label}>, <&clk0_ad9523 {fmc.adc_device_clk_idx}>, <&clk0_ad9523 {fmc.adc_sysref_clk_idx}>;\n"
            '\t\t\tclock-names = "jesd_adc_clk", "adc_clk", "adc_sysref";\n'
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <0>;\n"
            "\t\t\tjesd204-link-ids = <0>;\n"
            f"\t\t\tjesd204-inputs = <&{fmc.adc_core_label} 0 {fmc.adc_jesd_link_id}>;\n"
            f"\t\t\tadi,converters-per-device = <{fmc.rx_m}>;\n"
            f"\t\t\tadi,lanes-per-device = <{fmc.rx_l}>;\n"
            "\t\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\t\tadi,octets-per-frame = <{fmc.rx_f}>;\n"
            "\t\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\t\tadi,frames-per-multiframe = <{fmc.rx_k}>;\n"
            "\t\t\tadi,converter-resolution = <14>;\n"
            f"\t\t\tadi,bits-per-sample = <{fmc.rx_np}>;\n"
            "\t\t\tadi,control-bits-per-sample = <2>;\n"
            "\t\t\tadi,subclass = <1>;\n"
            f"\t\t\tadi,sampling-frequency = /bits/ 64 <{fmc.adc_sampling_frequency_hz}>;\n"
            "\t\t\tadi,input-clock-divider-ratio = <1>;\n"
            f"{adc_gpio_lines}"
            "\t\t};\n"
            f"\t\tdac0_ad9144: ad9144@{fmc.dac_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9144";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            f"\t\t\treg = <{fmc.dac_cs}>;\n"
            f"\t\t\tspi-max-frequency = <{fmc.dac_spi_max}>;\n"
            f"\t\t\tclocks = <&clk0_ad9523 {fmc.dac_device_clk_idx}>;\n"
            '\t\t\tclock-names = "dac_clk";\n'
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <1>;\n"
            "\t\t\tjesd204-link-ids = <0>;\n"
            f"\t\t\tjesd204-inputs = <&{fmc.dac_core_label} 1 {fmc.dac_jesd_link_id}>;\n"
            "\t\t\tadi,subclass = <1>;\n"
            "\t\t\tadi,interpolation = <1>;\n"
            f"{dac_gpio_lines}"
            "\t\t};\n"
            "\t};",
            f"\t&{fmc.adc_dma_label} {{\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{fmc.dac_dma_label} {{\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{fmc.adc_core_label} {{\n"
            '\t\tcompatible = "adi,axi-ad9680-1.0";\n'
            f"\t\tdmas = <&{fmc.adc_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t\tspibus-connected = <&adc0_ad9680>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{fmc.adc_jesd_label} 0 {fmc.adc_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.dac_core_label} {{\n"
            '\t\tcompatible = "adi,axi-ad9144-1.0";\n'
            f"\t\tdmas = <&{fmc.dac_dma_label} 0>;\n"
            '\t\tdma-names = "tx";\n'
            "\t\tspibus-connected = <&dac0_ad9144>;\n"
            "\t\tadi,axi-pl-fifo-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{fmc.dac_jesd_label} 1 {fmc.dac_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.adc_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, <&{fmc.adc_xcvr_label} 1>, <&{fmc.adc_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            '\t\tclock-output-names = "jesd_adc_lane_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\tadi,octets-per-frame = <{fmc.rx_f}>;\n"
            "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\tadi,frames-per-multiframe = <{fmc.rx_k}>;\n"
            f"\t\tjesd204-inputs = <&{fmc.adc_xcvr_label} 0 {fmc.adc_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.dac_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, <&{fmc.dac_xcvr_label} 1>, <&{fmc.dac_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            '\t\tclock-output-names = "jesd_dac_lane_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\tadi,octets-per-frame = <{fmc.tx_f}>;\n"
            "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\tadi,frames-per-multiframe = <{fmc.tx_k}>;\n"
            "\t\tadi,converter-resolution = <14>;\n"
            f"\t\tadi,bits-per-sample = <{fmc.tx_np}>;\n"
            f"\t\tadi,converters-per-device = <{fmc.tx_m}>;\n"
            "\t\tadi,control-bits-per-sample = <2>;\n"
            f"\t\tjesd204-inputs = <&{fmc.dac_xcvr_label} 1 {fmc.dac_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.adc_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&clk0_ad9523 {fmc.adc_xcvr_ref_clk_idx}>, <&clk0_ad9523 {fmc.adc_xcvr_ref_clk_idx}>;\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "adc_gt_clk", "rx_out_clk";\n'
            f"\t\tadi,sys-clk-select = <{fmc.adc_sys_clk_select}>;\n"
            f"\t\tadi,out-clk-select = <{fmc.adc_out_clk_select}>;\n"
            f"\t\tadi,jesd-l = <{fmc.rx_l}>;\n"
            f"\t\tadi,jesd-m = <{fmc.rx_m}>;\n"
            f"\t\tadi,jesd-s = <{fmc.rx_s}>;\n"
            "\t\tadi,use-lpm-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
            f"\t&{fmc.dac_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&clk0_ad9523 {fmc.dac_xcvr_ref_clk_idx}>, <&clk0_ad9523 {fmc.dac_xcvr_ref_clk_idx}>;\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "dac_gt_clk", "tx_out_clk";\n'
            f"\t\tadi,sys-clk-select = <{fmc.dac_sys_clk_select}>;\n"
            f"\t\tadi,out-clk-select = <{fmc.dac_out_clk_select}>;\n"
            f"\t\tadi,jesd-l = <{fmc.tx_l}>;\n"
            f"\t\tadi,jesd-m = <{fmc.tx_m}>;\n"
            f"\t\tadi,jesd-s = <{fmc.tx_s}>;\n"
            "\t\tadi,use-lpm-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
        ]

    def _build_fmcdaq2_cfg(self, cfg: dict[str, Any]) -> _FMCDAQ2Cfg:
        """Extract and coerce all FMCDAQ2 board parameters from *cfg* into an _FMCDAQ2Cfg."""
        board_cfg = cfg.get("fmcdaq2_board", {})

        def board_int(key: str, default: Any) -> int:
            return self._coerce_board_int(
                board_cfg.get(key, default), f"fmcdaq2_board.{key}"
            )

        jesd_cfg = cfg.get("jesd", {})
        rx_jesd_cfg = jesd_cfg.get("rx", {})
        tx_jesd_cfg = jesd_cfg.get("tx", {})
        rx_l = int(rx_jesd_cfg.get("L", 4))
        rx_m = int(rx_jesd_cfg.get("M", 2))
        rx_f = int(rx_jesd_cfg.get("F", 1))
        rx_k = int(rx_jesd_cfg.get("K", 32))
        rx_np = int(rx_jesd_cfg.get("Np", 16))
        rx_s = int(rx_jesd_cfg.get("S", 1))
        tx_l = int(tx_jesd_cfg.get("L", 4))
        tx_m = int(tx_jesd_cfg.get("M", 2))
        tx_f = int(tx_jesd_cfg.get("F", 1))
        tx_k = int(tx_jesd_cfg.get("K", 32))
        tx_np = int(tx_jesd_cfg.get("Np", 16))
        tx_s = int(tx_jesd_cfg.get("S", 1))
        sys_clk_map = {"XCVR_CPLL": 0, "XCVR_QPLL1": 2, "XCVR_QPLL": 3, "XCVR_QPLL0": 3}
        out_clk_map = {"XCVR_REFCLK": 4, "XCVR_REFCLK_DIV2": 4}
        fpga_adc = cfg.get("fpga_adc", {})
        fpga_dac = cfg.get("fpga_dac", {})
        adc_sys_clk_select = int(
            sys_clk_map.get(str(fpga_adc.get("sys_clk_select", "XCVR_CPLL")).upper(), 0)
        )
        dac_sys_clk_select = int(
            sys_clk_map.get(str(fpga_dac.get("sys_clk_select", "XCVR_QPLL")).upper(), 3)
        )
        adc_out_clk_select = int(
            out_clk_map.get(
                str(fpga_adc.get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(), 4
            )
        )
        dac_out_clk_select = int(
            out_clk_map.get(
                str(fpga_dac.get("out_clk_select", "XCVR_REFCLK_DIV2")).upper(), 4
            )
        )
        return _FMCDAQ2Cfg(
            spi_bus=str(board_cfg.get("spi_bus", "spi0")),
            clock_cs=board_int("clock_cs", 0),
            adc_cs=board_int("adc_cs", 2),
            dac_cs=board_int("dac_cs", 1),
            clock_vcxo_hz=board_int("clock_vcxo_hz", 125000000),
            clock_spi_max=board_int("clock_spi_max_frequency", 10000000),
            adc_spi_max=board_int("adc_spi_max_frequency", 1000000),
            dac_spi_max=board_int("dac_spi_max_frequency", 1000000),
            adc_dma_label=str(board_cfg.get("adc_dma_label", "axi_ad9680_dma")),
            dac_dma_label=str(board_cfg.get("dac_dma_label", "axi_ad9144_dma")),
            adc_core_label=str(board_cfg.get("adc_core_label", "axi_ad9680_core")),
            dac_core_label=str(board_cfg.get("dac_core_label", "axi_ad9144_core")),
            adc_xcvr_label=str(board_cfg.get("adc_xcvr_label", "axi_ad9680_adxcvr")),
            dac_xcvr_label=str(board_cfg.get("dac_xcvr_label", "axi_ad9144_adxcvr")),
            adc_jesd_label=str(
                board_cfg.get("adc_jesd_label", "axi_ad9680_jesd204_rx")
            ),
            dac_jesd_label=str(
                board_cfg.get("dac_jesd_label", "axi_ad9144_jesd204_tx")
            ),
            adc_jesd_link_id=board_int("adc_jesd_link_id", 0),
            dac_jesd_link_id=board_int("dac_jesd_link_id", 0),
            gpio_controller=str(board_cfg.get("gpio_controller", "gpio0")),
            adc_device_clk_idx=board_int("adc_device_clk_idx", 13),
            adc_sysref_clk_idx=board_int("adc_sysref_clk_idx", 5),
            adc_xcvr_ref_clk_idx=board_int("adc_xcvr_ref_clk_idx", 4),
            adc_sampling_frequency_hz=board_int(
                "adc_sampling_frequency_hz", 1000000000
            ),
            dac_device_clk_idx=board_int("dac_device_clk_idx", 1),
            dac_xcvr_ref_clk_idx=board_int("dac_xcvr_ref_clk_idx", 9),
            clk_sync_gpio=board_cfg.get("clk_sync_gpio"),
            clk_status0_gpio=board_cfg.get("clk_status0_gpio"),
            clk_status1_gpio=board_cfg.get("clk_status1_gpio"),
            dac_txen_gpio=board_cfg.get("dac_txen_gpio"),
            dac_reset_gpio=board_cfg.get("dac_reset_gpio"),
            dac_irq_gpio=board_cfg.get("dac_irq_gpio"),
            adc_powerdown_gpio=board_cfg.get("adc_powerdown_gpio"),
            adc_fastdetect_a_gpio=board_cfg.get("adc_fastdetect_a_gpio"),
            adc_fastdetect_b_gpio=board_cfg.get("adc_fastdetect_b_gpio"),
            rx_l=rx_l,
            rx_m=rx_m,
            rx_f=rx_f,
            rx_k=rx_k,
            rx_np=rx_np,
            rx_s=rx_s,
            tx_l=tx_l,
            tx_m=tx_m,
            tx_f=tx_f,
            tx_k=tx_k,
            tx_np=tx_np,
            tx_s=tx_s,
            adc_sys_clk_select=adc_sys_clk_select,
            dac_sys_clk_select=dac_sys_clk_select,
            adc_out_clk_select=adc_out_clk_select,
            dac_out_clk_select=dac_out_clk_select,
        )

    def _build_fmcdaq3_nodes(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> list[str]:
        """Build DTS node strings for an FMCDAQ3 (AD9528 + AD9680 + AD9152) design.

        Returns an empty list if the topology is not an FMCDAQ3 design.
        """
        if not topology.is_fmcdaq3_design():
            return []

        fmc = self._build_fmcdaq3_cfg(cfg)
        clk_gpio_lines = self._format_optional_gpio_lines(
            fmc.gpio_controller,
            [
                ("status0-gpios", fmc.clk_status0_gpio, "clk_status0_gpio"),
                ("status1-gpios", fmc.clk_status1_gpio, "clk_status1_gpio"),
            ],
        )
        dac_gpio_lines = self._format_optional_gpio_lines(
            fmc.gpio_controller,
            [
                ("txen-gpios", fmc.dac_txen_gpio, "dac_txen_gpio"),
                ("irq-gpios", fmc.dac_irq_gpio, "dac_irq_gpio"),
            ],
        )
        adc_gpio_lines = self._format_optional_gpio_lines(
            fmc.gpio_controller,
            [
                ("powerdown-gpios", fmc.adc_powerdown_gpio, "adc_powerdown_gpio"),
                (
                    "fastdetect-a-gpios",
                    fmc.adc_fastdetect_a_gpio,
                    "adc_fastdetect_a_gpio",
                ),
                (
                    "fastdetect-b-gpios",
                    fmc.adc_fastdetect_b_gpio,
                    "adc_fastdetect_b_gpio",
                ),
            ],
        )

        return [
            f"\t&{fmc.spi_bus} {{\n"
            '\t\tstatus = "okay";\n'
            f"\t\tclk0_ad9528: ad9528@{fmc.clock_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9528";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            f"\t\t\treg = <{fmc.clock_cs}>;\n"
            f"\t\t\tspi-max-frequency = <{fmc.clock_spi_max}>;\n"
            "\t\t\tadi,spi-3wire-enable;\n"
            '\t\t\tclock-output-names = "ad9528_out0", "ad9528_out1", "ad9528_out2", '
            '"ad9528_out3", "ad9528_out4", "ad9528_out5", "ad9528_out6", '
            '"ad9528_out7", "ad9528_out8", "ad9528_out9", "ad9528_out10", '
            '"ad9528_out11", "ad9528_out12", "ad9528_out13";\n'
            "\t\t\t#clock-cells = <1>;\n"
            f"\t\t\tadi,vcxo-freq = <{fmc.clock_vcxo_hz}>;\n"
            "\t\t\tadi,pll1-bypass-enable;\n"
            "\t\t\tadi,osc-in-diff-enable;\n"
            "\t\t\tadi,pll2-m1-frequency = <1233333333>;\n"
            "\t\t\tadi,pll2-charge-pump-current-nA = <35000>;\n"
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-sysref-provider;\n"
            f"{clk_gpio_lines}"
            f"{self._fmcdaq3_ad9528_channels_block()}"
            "\t\t};\n"
            f"\t\tdac0_ad9152: ad9152@{fmc.dac_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9152";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            f"\t\t\treg = <{fmc.dac_cs}>;\n"
            "\t\t\tspi-cpol;\n"
            "\t\t\tspi-cpha;\n"
            f"\t\t\tspi-max-frequency = <{fmc.dac_spi_max}>;\n"
            "\t\t\tadi,spi-3wire-enable;\n"
            f"\t\t\tclocks = <&clk0_ad9528 {fmc.dac_device_clk_idx}>;\n"
            '\t\t\tclock-names = "dac_clk";\n'
            f"\t\t\tadi,jesd-link-mode = <{fmc.ad9152_jesd_link_mode}>;\n"
            "\t\t\tadi,subclass = <1>;\n"
            "\t\t\tadi,interpolation = <1>;\n"
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <1>;\n"
            "\t\t\tjesd204-link-ids = <0>;\n"
            f"\t\t\tjesd204-inputs = <&{fmc.dac_core_label} 1 {fmc.dac_jesd_link_id}>;\n"
            f"{dac_gpio_lines}"
            "\t\t};\n"
            f"\t\tadc0_ad9680: ad9680@{fmc.adc_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9680";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            f"\t\t\treg = <{fmc.adc_cs}>;\n"
            "\t\t\tspi-cpol;\n"
            "\t\t\tspi-cpha;\n"
            f"\t\t\tspi-max-frequency = <{fmc.adc_spi_max}>;\n"
            "\t\t\tadi,spi-3wire-enable;\n"
            f"\t\t\tclocks = <&clk0_ad9528 {fmc.adc_device_clk_idx}>;\n"
            '\t\t\tclock-names = "adc_clk";\n'
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <0>;\n"
            "\t\t\tjesd204-link-ids = <0>;\n"
            f"\t\t\tjesd204-inputs = <&{fmc.adc_core_label} 0 {fmc.adc_jesd_link_id}>;\n"
            f"\t\t\tadi,converters-per-device = <{fmc.rx_m}>;\n"
            f"\t\t\tadi,lanes-per-device = <{fmc.rx_l}>;\n"
            "\t\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\t\tadi,octets-per-frame = <{fmc.rx_f}>;\n"
            "\t\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\t\tadi,frames-per-multiframe = <{fmc.rx_k}>;\n"
            "\t\t\tadi,converter-resolution = <14>;\n"
            f"\t\t\tadi,bits-per-sample = <{fmc.rx_np}>;\n"
            "\t\t\tadi,control-bits-per-sample = <2>;\n"
            "\t\t\tadi,subclass = <1>;\n"
            f"\t\t\tadi,sampling-frequency = /bits/ 64 <{fmc.adc_sampling_frequency_hz}>;\n"
            "\t\t\tadi,input-clock-divider-ratio = <1>;\n"
            "\t\t\tadi,sysref-lmfc-offset = <0>;\n"
            "\t\t\tadi,sysref-pos-window-skew = <0>;\n"
            "\t\t\tadi,sysref-neg-window-skew = <0>;\n"
            "\t\t\tadi,sysref-mode = <1>;\n"
            "\t\t\tadi,sysref-nshot-ignore-count = <0>;\n"
            f"{adc_gpio_lines}"
            "\t\t};\n"
            "\t};",
            f"\t&{fmc.adc_dma_label} {{\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{fmc.dac_dma_label} {{\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{fmc.adc_core_label} {{\n"
            '\t\tcompatible = "adi,axi-ad9680-1.0";\n'
            f"\t\tdmas = <&{fmc.adc_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t\tspibus-connected = <&adc0_ad9680>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{fmc.adc_jesd_label} 0 {fmc.adc_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.dac_core_label} {{\n"
            '\t\tcompatible = "adi,axi-ad9144-1.0";\n'
            f"\t\tdmas = <&{fmc.dac_dma_label} 0>;\n"
            '\t\tdma-names = "tx";\n'
            "\t\tspibus-connected = <&dac0_ad9152>;\n"
            "\t\tadi,axi-pl-fifo-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{fmc.dac_jesd_label} 1 {fmc.dac_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.adc_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, <&{fmc.adc_xcvr_label} 1>, <&{fmc.adc_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            '\t\tclock-output-names = "jesd_adc_lane_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\tadi,octets-per-frame = <{fmc.rx_f}>;\n"
            "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\tadi,frames-per-multiframe = <{fmc.rx_k}>;\n"
            f"\t\tjesd204-inputs = <&{fmc.adc_xcvr_label} 0 {fmc.adc_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.dac_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, <&{fmc.dac_xcvr_label} 1>, <&{fmc.dac_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            '\t\tclock-output-names = "jesd_dac_lane_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tadi,octets-per-frame = <{fmc.tx_f}>;\n"
            f"\t\tadi,frames-per-multiframe = <{fmc.tx_k}>;\n"
            f"\t\tadi,converters-per-device = <{fmc.tx_m}>;\n"
            f"\t\tadi,bits-per-sample = <{fmc.tx_np}>;\n"
            "\t\tadi,control-bits-per-sample = <2>;\n"
            f"\t\tjesd204-inputs = <&{fmc.dac_xcvr_label} 1 {fmc.dac_jesd_link_id}>;\n"
            "\t};",
            f"\t&{fmc.adc_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&clk0_ad9528 {fmc.adc_xcvr_ref_clk_idx}>;\n"
            '\t\tclock-names = "conv";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "adc_gt_clk", "rx_out_clk";\n'
            f"\t\tadi,sys-clk-select = <{fmc.adc_sys_clk_select}>;\n"
            f"\t\tadi,out-clk-select = <{fmc.adc_out_clk_select}>;\n"
            "\t\tadi,use-lpm-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\tjesd204-inputs = <&clk0_ad9528 0 0>;\n"
            "\t};",
            f"\t&{fmc.dac_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&clk0_ad9528 {fmc.dac_xcvr_ref_clk_idx}>;\n"
            '\t\tclock-names = "conv";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "dac_gt_clk", "tx_out_clk";\n'
            f"\t\tadi,sys-clk-select = <{fmc.dac_sys_clk_select}>;\n"
            f"\t\tadi,out-clk-select = <{fmc.dac_out_clk_select}>;\n"
            "\t\tadi,use-lpm-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
        ]

    def _build_fmcdaq3_cfg(self, cfg: dict[str, Any]) -> _FMCDAQ3Cfg:
        """Extract and coerce all FMCDAQ3 board parameters from *cfg* into an _FMCDAQ3Cfg."""
        board_cfg = cfg.get("fmcdaq3_board", {})

        def board_int(key: str, default: Any) -> int:
            return self._coerce_board_int(
                board_cfg.get(key, default), f"fmcdaq3_board.{key}"
            )

        jesd_cfg = cfg.get("jesd", {})
        rx_jesd_cfg = jesd_cfg.get("rx", {})
        tx_jesd_cfg = jesd_cfg.get("tx", {})
        rx_l = int(rx_jesd_cfg.get("L", 4))
        rx_m = int(rx_jesd_cfg.get("M", 2))
        rx_f = int(rx_jesd_cfg.get("F", 1))
        rx_k = int(rx_jesd_cfg.get("K", 32))
        rx_np = int(rx_jesd_cfg.get("Np", 16))
        rx_s = int(rx_jesd_cfg.get("S", 1))
        tx_l = int(tx_jesd_cfg.get("L", 4))
        tx_m = int(tx_jesd_cfg.get("M", 2))
        tx_f = int(tx_jesd_cfg.get("F", 1))
        tx_k = int(tx_jesd_cfg.get("K", 32))
        tx_np = int(tx_jesd_cfg.get("Np", 16))
        tx_s = int(tx_jesd_cfg.get("S", 1))
        sys_clk_map = {"XCVR_CPLL": 0, "XCVR_QPLL1": 2, "XCVR_QPLL": 3, "XCVR_QPLL0": 3}
        out_clk_map = {"XCVR_REFCLK": 4, "XCVR_PROGDIV_CLK": 8, "XCVR_REFCLK_DIV2": 4}
        fpga_adc = cfg.get("fpga_adc", {})
        fpga_dac = cfg.get("fpga_dac", {})
        adc_sys_clk_select = int(
            sys_clk_map.get(str(fpga_adc.get("sys_clk_select", "XCVR_CPLL")).upper(), 0)
        )
        dac_sys_clk_select = int(
            sys_clk_map.get(str(fpga_dac.get("sys_clk_select", "XCVR_QPLL")).upper(), 3)
        )
        adc_out_clk_select = int(
            out_clk_map.get(
                str(fpga_adc.get("out_clk_select", "XCVR_PROGDIV_CLK")).upper(), 8
            )
        )
        dac_out_clk_select = int(
            out_clk_map.get(
                str(fpga_dac.get("out_clk_select", "XCVR_PROGDIV_CLK")).upper(), 8
            )
        )
        return _FMCDAQ3Cfg(
            spi_bus=str(board_cfg.get("spi_bus", "spi0")),
            clock_cs=board_int("clock_cs", 0),
            adc_cs=board_int("adc_cs", 2),
            dac_cs=board_int("dac_cs", 1),
            clock_vcxo_hz=board_int("clock_vcxo_hz", 100000000),
            clock_spi_max=board_int("clock_spi_max_frequency", 10000000),
            adc_spi_max=board_int("adc_spi_max_frequency", 10000000),
            dac_spi_max=board_int("dac_spi_max_frequency", 10000000),
            adc_dma_label=str(board_cfg.get("adc_dma_label", "axi_ad9680_dma")),
            dac_dma_label=str(board_cfg.get("dac_dma_label", "axi_ad9152_dma")),
            adc_core_label=str(
                board_cfg.get("adc_core_label", "axi_ad9680_tpl_core_adc_tpl_core")
            ),
            dac_core_label=str(
                board_cfg.get("dac_core_label", "axi_ad9152_tpl_core_dac_tpl_core")
            ),
            adc_xcvr_label=str(board_cfg.get("adc_xcvr_label", "axi_ad9680_xcvr")),
            dac_xcvr_label=str(board_cfg.get("dac_xcvr_label", "axi_ad9152_xcvr")),
            adc_jesd_label=str(
                board_cfg.get("adc_jesd_label", "axi_ad9680_jesd_rx_axi")
            ),
            dac_jesd_label=str(
                board_cfg.get("dac_jesd_label", "axi_ad9152_jesd_tx_axi")
            ),
            adc_jesd_link_id=board_int("adc_jesd_link_id", 0),
            dac_jesd_link_id=board_int("dac_jesd_link_id", 0),
            gpio_controller=str(board_cfg.get("gpio_controller", "gpio")),
            adc_device_clk_idx=board_int("adc_device_clk_idx", 13),
            adc_xcvr_ref_clk_idx=board_int("adc_xcvr_ref_clk_idx", 9),
            adc_sampling_frequency_hz=board_int(
                "adc_sampling_frequency_hz", 1233333333
            ),
            dac_device_clk_idx=board_int("dac_device_clk_idx", 2),
            dac_xcvr_ref_clk_idx=board_int("dac_xcvr_ref_clk_idx", 4),
            clk_status0_gpio=board_cfg.get("clk_status0_gpio"),
            clk_status1_gpio=board_cfg.get("clk_status1_gpio"),
            dac_txen_gpio=board_cfg.get("dac_txen_gpio"),
            dac_irq_gpio=board_cfg.get("dac_irq_gpio"),
            adc_powerdown_gpio=board_cfg.get("adc_powerdown_gpio"),
            adc_fastdetect_a_gpio=board_cfg.get("adc_fastdetect_a_gpio"),
            adc_fastdetect_b_gpio=board_cfg.get("adc_fastdetect_b_gpio"),
            rx_l=rx_l,
            rx_m=rx_m,
            rx_f=rx_f,
            rx_k=rx_k,
            rx_np=rx_np,
            rx_s=rx_s,
            tx_l=tx_l,
            tx_m=tx_m,
            tx_f=tx_f,
            tx_k=tx_k,
            tx_np=tx_np,
            tx_s=tx_s,
            ad9152_jesd_link_mode=board_int("ad9152_jesd_link_mode", 4),
            adc_sys_clk_select=adc_sys_clk_select,
            dac_sys_clk_select=dac_sys_clk_select,
            adc_out_clk_select=adc_out_clk_select,
            dac_out_clk_select=dac_out_clk_select,
        )

    def _build_ad9172_nodes(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> list[str]:
        """Build DTS node strings for an AD9172 DAC design with HMC7044 clock chip.

        Returns an empty list if neither the topology nor *cfg* indicate an AD9172 design.
        """
        if not (self._is_ad9172_design(topology) or ("ad9172_board" in cfg)):
            return []

        ad = self._build_ad9172_cfg(cfg, topology)
        return [
            f"\t&{ad.spi_bus} {{\n"
            '\t\tstatus = "okay";\n'
            f"\t\thmc7044: hmc7044@{ad.clock_cs} {{\n"
            '\t\t\tcompatible = "adi,hmc7044";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            "\t\t\t#clock-cells = <1>;\n"
            f"\t\t\treg = <{ad.clock_cs}>;\n"
            f"\t\t\tspi-max-frequency = <{ad.clock_spi_max}>;\n"
            f"\t\t\tadi,pll1-clkin-frequencies = <{ad.hmc7044_ref_clk_hz} 0 0 0>;\n"
            "\t\t\tadi,pll1-loop-bandwidth-hz = <200>;\n"
            f"\t\t\tadi,vcxo-frequency = <{ad.hmc7044_vcxo_hz}>;\n"
            f"\t\t\tadi,pll2-output-frequency = <{ad.hmc7044_out_freq_hz}>;\n"
            "\t\t\tadi,sysref-timer-divider = <1024>;\n"
            "\t\t\tadi,pulse-generator-mode = <0>;\n"
            "\t\t\tadi,clkin0-buffer-mode = <0x15>;\n"
            "\t\t\tadi,oscin-buffer-mode = <0x15>;\n"
            "\t\t\tadi,gpi-controls = <0x00 0x00 0x00 0x00>;\n"
            "\t\t\tadi,gpo-controls = <0x1f 0x2b 0x00 0x00>;\n"
            '\t\t\tclock-output-names = "hmc7044_out0", "hmc7044_out1", "hmc7044_out2", '
            '"hmc7044_out3", "hmc7044_out4", "hmc7044_out5", "hmc7044_out6", '
            '"hmc7044_out7", "hmc7044_out8", "hmc7044_out9", "hmc7044_out10", '
            '"hmc7044_out11", "hmc7044_out12", "hmc7044_out13";\n'
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-sysref-provider;\n"
            "\t\t\tadi,jesd204-max-sysref-frequency-hz = <2000000>;\n"
            "\t\t\thmc7044_c2: channel@2 {\n"
            "\t\t\t\treg = <2>;\n"
            '\t\t\t\tadi,extended-name = "DAC_CLK";\n'
            f"\t\t\t\tadi,divider = <8>; // {self._fmt_hz(ad.hmc7044_out_freq_hz // 8)}\n"
            "\t\t\t\tadi,driver-mode = <1>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c3: channel@3 {\n"
            "\t\t\t\treg = <3>;\n"
            '\t\t\t\tadi,extended-name = "DAC_SYSREF";\n'
            f"\t\t\t\tadi,divider = <512>; // {self._fmt_hz(ad.hmc7044_out_freq_hz // 512)}\n"
            "\t\t\t\tadi,driver-mode = <1>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c12: channel@12 {\n"
            "\t\t\t\treg = <12>;\n"
            '\t\t\t\tadi,extended-name = "FPGA_CLK";\n'
            f"\t\t\t\tadi,divider = <8>; // {self._fmt_hz(ad.hmc7044_out_freq_hz // 8)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c13: channel@13 {\n"
            "\t\t\t\treg = <13>;\n"
            '\t\t\t\tadi,extended-name = "FPGA_SYSREF";\n'
            f"\t\t\t\tadi,divider = <512>; // {self._fmt_hz(ad.hmc7044_out_freq_hz // 512)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
            "\t\t};\n"
            f"\t\tdac0_ad9172: ad9172@{ad.dac_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9172";\n'
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            f"\t\t\treg = <{ad.dac_cs}>;\n"
            f"\t\t\tspi-max-frequency = <{ad.dac_spi_max}>;\n"
            "\t\t\tclocks = <&hmc7044 2>;\n"
            '\t\t\tclock-names = "dac_clk";\n'
            f"\t\t\tadi,dac-rate-khz = <{ad.ad9172_dac_rate_khz}>;\n"
            f"\t\t\tadi,jesd-link-mode = <{ad.ad9172_jesd_link_mode}>;\n"
            "\t\t\tadi,jesd-subclass = <1>;\n"
            f"\t\t\tadi,dac-interpolation = <{ad.ad9172_dac_interpolation}>;\n"
            f"\t\t\tadi,channel-interpolation = <{ad.ad9172_channel_interpolation}>;\n"
            f"\t\t\tadi,clock-output-divider = <{ad.ad9172_clock_output_divider}>;\n"
            "\t\t\tadi,syncoutb-signal-type-lvds-enable;\n"
            "\t\t\tadi,scrambling = <1>;\n"
            "\t\t\tadi,sysref-mode = <2>;\n"
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <0>;\n"
            "\t\t\tjesd204-link-ids = <0>;\n"
            f"\t\t\tjesd204-inputs = <&{ad.dac_core_label} 0 {ad.dac_jesd_link_id}>;\n"
            "\t\t};\n"
            "\t};",
            f"\t&{ad.dac_core_label} {{\n"
            '\t\tcompatible = "adi,axi-ad9172-1.0";\n'
            "\t\tspibus-connected = <&dac0_ad9172>;\n"
            "\t\tadi,axi-pl-fifo-enable;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&{ad.dac_jesd_label} 0 {ad.dac_jesd_link_id}>;\n"
            "\t};",
            f"\t&{ad.dac_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, <&{ad.dac_xcvr_label} 1>, <&{ad.dac_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            '\t\tclock-output-names = "jesd_dac_lane_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\tadi,octets-per-frame = <{ad.tx_f}>;\n"
            "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\tadi,frames-per-multiframe = <{ad.tx_k}>;\n"
            f"\t\tadi,converters-per-device = <{ad.tx_m}>;\n"
            f"\t\tadi,bits-per-sample = <{ad.tx_np}>;\n"
            "\t\tadi,control-bits-per-sample = <0>;\n"
            f"\t\tjesd204-inputs = <&{ad.dac_xcvr_label} 0 {ad.dac_jesd_link_id}>;\n"
            "\t};",
            f"\t&{ad.dac_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            "\t\tclocks = <&hmc7044 12>;\n"
            '\t\tclock-names = "conv";\n'
            "\t\tadi,sys-clk-select = <3>;\n"
            "\t\tadi,out-clk-select = <4>;\n"
            "\t\tadi,use-lpm-enable;\n"
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "dac_gt_clk", "tx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\tjesd204-inputs = <&hmc7044 0 0>;\n"
            "\t};",
        ]

    def _build_ad9172_cfg(
        self, cfg: dict[str, Any], topology: XsaTopology
    ) -> _AD9172Cfg:
        """Derive label names and extract AD9172 board parameters from *cfg* and *topology*."""
        board_cfg = cfg.get("ad9172_board", {})
        tx_cfg = cfg.get("jesd", {}).get("tx", {})
        tx_label = str(board_cfg.get("dac_jesd_label", "axi_ad9172_jesd_tx_axi"))
        xcvr_label = str(board_cfg.get("dac_xcvr_label", "axi_ad9172_adxcvr"))
        core_label = str(board_cfg.get("dac_core_label", "axi_ad9172_core"))
        if topology.jesd204_tx:
            inferred_tx = topology.jesd204_tx[0].name.replace("-", "_")
            tx_label = str(board_cfg.get("dac_jesd_label", inferred_tx))
            topology_names = self._topology_instance_names(topology)
            inferred_xcvr = self._infer_ad9172_xcvr_label(tx_label)
            inferred_core = self._infer_ad9172_core_label(tx_label)
            if topology_names:
                inferred_xcvr = self._pick_existing_ad9172_label(
                    topology_names,
                    inferred_xcvr,
                    tx_label,
                    ("xcvr",),
                )
                inferred_core = self._pick_existing_ad9172_label(
                    topology_names,
                    inferred_core,
                    tx_label,
                    ("transport", "tpl", "core"),
                )
            xcvr_label = str(board_cfg.get("dac_xcvr_label", inferred_xcvr))
            core_label = str(board_cfg.get("dac_core_label", inferred_core))
        return _AD9172Cfg(
            spi_bus=str(board_cfg.get("spi_bus", "spi0")),
            clock_cs=int(board_cfg.get("clock_cs", 0)),
            dac_cs=int(board_cfg.get("dac_cs", 1)),
            clock_spi_max=int(board_cfg.get("clock_spi_max_frequency", 10000000)),
            dac_spi_max=int(board_cfg.get("dac_spi_max_frequency", 1000000)),
            dac_core_label=core_label,
            dac_xcvr_label=xcvr_label,
            dac_jesd_label=tx_label,
            dac_jesd_link_id=int(board_cfg.get("dac_jesd_link_id", 0)),
            hmc7044_ref_clk_hz=int(board_cfg.get("hmc7044_ref_clk_hz", 122880000)),
            hmc7044_vcxo_hz=int(board_cfg.get("hmc7044_vcxo_hz", 122880000)),
            hmc7044_out_freq_hz=int(board_cfg.get("hmc7044_out_freq_hz", 2949120000)),
            ad9172_dac_rate_khz=int(board_cfg.get("ad9172_dac_rate_khz", 11796480)),
            ad9172_jesd_link_mode=int(board_cfg.get("ad9172_jesd_link_mode", 4)),
            ad9172_dac_interpolation=int(board_cfg.get("ad9172_dac_interpolation", 8)),
            ad9172_channel_interpolation=int(
                board_cfg.get("ad9172_channel_interpolation", 4)
            ),
            ad9172_clock_output_divider=int(
                board_cfg.get("ad9172_clock_output_divider", 4)
            ),
            tx_l=int(tx_cfg.get("L", 4)),
            tx_m=int(tx_cfg.get("M", 4)),
            tx_f=int(tx_cfg.get("F", 2)),
            tx_k=int(tx_cfg.get("K", 32)),
            tx_np=int(tx_cfg.get("Np", 16)),
        )

    @staticmethod
    def _topology_instance_names(topology: XsaTopology) -> set[str]:
        """Return the union of all IP instance and signal-connection participant names from the topology.

        All names have hyphens replaced with underscores to match DTS label conventions.
        """
        names: set[str] = set()
        names.update(i.name.replace("-", "_") for i in topology.jesd204_tx)
        names.update(i.name.replace("-", "_") for i in topology.jesd204_rx)
        names.update(i.name.replace("-", "_") for i in topology.clkgens)
        names.update(i.name.replace("-", "_") for i in topology.converters)
        for conn in topology.signal_connections:
            names.update(n.replace("-", "_") for n in conn.producers)
            names.update(n.replace("-", "_") for n in conn.consumers)
            names.update(n.replace("-", "_") for n in conn.bidirectional)
        return names

    @staticmethod
    def _infer_ad9172_xcvr_label(tx_label: str) -> str:
        """Derive the XCVR label from the TX JESD label using AD9172 naming conventions."""
        if "_link_tx_axi" in tx_label:
            return tx_label.replace("_link_tx_axi", "_xcvr")
        if "_jesd_tx_axi" in tx_label:
            return tx_label.replace("_jesd_tx_axi", "_adxcvr")
        return tx_label.replace("_jesd", "_adxcvr")

    @staticmethod
    def _infer_ad9172_core_label(tx_label: str) -> str:
        """Derive the DAC TPL core label from the TX JESD label using AD9172 naming conventions."""
        if "_link_tx_axi" in tx_label:
            return tx_label.replace("_link_tx_axi", "_transport_dac_tpl_core")
        if "_jesd_tx_axi" in tx_label:
            return tx_label.replace("_jesd_tx_axi", "_core")
        return tx_label.replace("_jesd_tx_axi", "_core").replace("_jesd", "_core")

    @staticmethod
    def _ad9172_prefix_from_tx_label(tx_label: str) -> str:
        """Strip known AD9172 TX-JESD suffixes from *tx_label* and return the common IP prefix."""
        for suffix in ("_link_tx_axi", "_jesd_tx_axi", "_jesd204_tx_axi", "_jesd_tx"):
            if tx_label.endswith(suffix):
                return tx_label[: -len(suffix)]
        return tx_label

    def _pick_existing_ad9172_label(
        self,
        topology_names: set[str],
        default: str,
        tx_label: str,
        required_keywords: tuple[str, ...],
    ) -> str:
        """Return the best topology name that shares the TX label's prefix and has all *required_keywords*.

        Falls back to *default* when no candidate is found or *default* is already present.
        """
        if default in topology_names:
            return default
        prefix = self._ad9172_prefix_from_tx_label(tx_label).lower()
        candidates = sorted(
            n
            for n in topology_names
            if prefix in n.lower()
            and all(keyword in n.lower() for keyword in required_keywords)
        )
        if candidates:
            return candidates[0]
        return default

    def _format_optional_gpio_lines(
        self, gpio_controller: str, gpio_mappings: list[tuple[str, Any, str]]
    ) -> str:
        """Render ``prop-name = <&gpio_controller idx 0>;`` lines for each non-None GPIO mapping."""
        lines = []
        for prop_name, value, cfg_key in gpio_mappings:
            if value is not None:
                gpio_idx = self._coerce_board_int(value, f"fmcdaq2_board.{cfg_key}")
                lines.append(
                    f"\t\t\t{prop_name} = <&{gpio_controller} {gpio_idx} 0>;\n"
                )
        return "".join(lines)

    @staticmethod
    def _pick_matching_label(
        topology_names: set[str], default: str, required_tokens: tuple[str, ...]
    ) -> str:
        """Return the first topology name containing all *required_tokens*, or *default* if none match.

        When *default* itself is already in *topology_names*, it is returned immediately.
        """
        if default in topology_names:
            return default
        candidates = sorted(
            n
            for n in topology_names
            if all(token in n.lower() for token in required_tokens)
        )
        return candidates[0] if candidates else default

    @staticmethod
    def _is_fmcomms8_layout(topology_names: set[str]) -> bool:
        """Return True if *topology_names* indicate a dual-chip FMComms8 ADRV9009 layout.

        Detected by the presence of per-direction ADRV9009 TPL core instances (rx/tx/obs).
        """
        return any(
            "tpl_core" in name.lower()
            and "adrv9009" in name.lower()
            and (
                "fmc" in name.lower()
                or "obs" in name.lower()
                or "rx" in name.lower()
                or "tx" in name.lower()
            )
            for name in topology_names
        )

    @staticmethod
    def _coerce_board_int(value: Any, key_path: str) -> int:
        """Convert *value* to int; raise ValueError with *key_path* context on failure."""
        if isinstance(value, bool):
            raise ValueError(f"{key_path} must be an integer, got {value!r}")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key_path} must be an integer, got {value!r}") from exc

    @staticmethod
    def _fmt_hz(hz: int) -> str:
        """Format *hz* as a human-readable frequency string (e.g. '245.76 MHz', '768 kHz')."""
        if hz >= 1_000_000_000:
            s = f"{hz / 1_000_000_000:.6f}".rstrip("0").rstrip(".")
            return f"{s} GHz"
        if hz >= 1_000_000:
            s = f"{hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
            return f"{s} MHz"
        if hz >= 1_000:
            s = f"{hz / 1_000:.3f}".rstrip("0").rstrip(".")
            return f"{s} kHz"
        return f"{hz} Hz"

    def _fmcdaq2_ad9523_channels_block(self) -> str:
        """Return the DTS channel sub-nodes string for the FMCDAQ2 AD9523-1 clock chip."""
        # PLL2 M1 distribution frequency: adi,pll2-m1-freq = <1000000000>
        _m1 = 1_000_000_000
        return (
            "\t\t\tad9523_0_c1:channel@1 {\n"
            "\t\t\t\treg = <1>;\n"
            '\t\t\t\tadi,extended-name = "DAC_CLK";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <1>; // {self._fmt_hz(_m1 // 1)}\n"
            "\t\t\t};\n"
            "\t\t\tad9523_0_c4:channel@4 {\n"
            "\t\t\t\treg = <4>;\n"
            '\t\t\t\tadi,extended-name = "ADC_CLK_FMC";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <2>; // {self._fmt_hz(_m1 // 2)}\n"
            "\t\t\t};\n"
            "\t\t\tad9523_0_c5:channel@5 {\n"
            "\t\t\t\treg = <5>;\n"
            '\t\t\t\tadi,extended-name = "ADC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <128>; // {self._fmt_hz(_m1 // 128)}\n"
            "\t\t\t};\n"
            "\t\t\tad9523_0_c6:channel@6 {\n"
            "\t\t\t\treg = <6>;\n"
            '\t\t\t\tadi,extended-name = "CLKD_ADC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <128>; // {self._fmt_hz(_m1 // 128)}\n"
            "\t\t\t};\n"
            "\t\t\tad9523_0_c7:channel@7 {\n"
            "\t\t\t\treg = <7>;\n"
            '\t\t\t\tadi,extended-name = "CLKD_DAC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <128>; // {self._fmt_hz(_m1 // 128)}\n"
            "\t\t\t};\n"
            "\t\t\tad9523_0_c8:channel@8 {\n"
            "\t\t\t\treg = <8>;\n"
            '\t\t\t\tadi,extended-name = "DAC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <128>; // {self._fmt_hz(_m1 // 128)}\n"
            "\t\t\t};\n"
            "\t\t\tad9523_0_c9:channel@9 {\n"
            "\t\t\t\treg = <9>;\n"
            '\t\t\t\tadi,extended-name = "FMC_DAC_REF_CLK";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <2>; // {self._fmt_hz(_m1 // 2)}\n"
            "\t\t\t};\n"
            "\t\t\tad9523_0_c13:channel@13 {\n"
            "\t\t\t\treg = <13>;\n"
            '\t\t\t\tadi,extended-name = "ADC_CLK";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <1>;\n"
            f"\t\t\t\tadi,channel-divider = <1>; // {self._fmt_hz(_m1 // 1)}\n"
            "\t\t\t};\n"
        )

    def _fmcdaq3_ad9528_channels_block(self) -> str:
        """Return the DTS channel sub-nodes string for the FMCDAQ3 AD9528 clock chip."""
        # PLL2 M1 distribution frequency: adi,pll2-m1-frequency = <1233333333>
        _m1 = 1_233_333_333
        return (
            "\t\t\tad9528_0_c2: channel@2 {\n"
            "\t\t\t\treg = <2>;\n"
            '\t\t\t\tadi,extended-name = "DAC_CLK";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            f"\t\t\t\tadi,channel-divider = <1>; // {self._fmt_hz(_m1 // 1)}\n"
            "\t\t\t\tadi,signal-source = <0>;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c4: channel@4 {\n"
            "\t\t\t\treg = <4>;\n"
            '\t\t\t\tadi,extended-name = "DAC_CLK_FMC";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            f"\t\t\t\tadi,channel-divider = <2>; // {self._fmt_hz(_m1 // 2)}\n"
            "\t\t\t\tadi,signal-source = <0>;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c5: channel@5 {\n"
            "\t\t\t\treg = <5>;\n"
            '\t\t\t\tadi,extended-name = "DAC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            "\t\t\t\tadi,channel-divider = <1>;\n"
            "\t\t\t\tadi,signal-source = <2>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c6: channel@6 {\n"
            "\t\t\t\treg = <6>;\n"
            '\t\t\t\tadi,extended-name = "CLKD_DAC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            "\t\t\t\tadi,channel-divider = <2>;\n"
            "\t\t\t\tadi,signal-source = <2>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c7: channel@7 {\n"
            "\t\t\t\treg = <7>;\n"
            '\t\t\t\tadi,extended-name = "CLKD_ADC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            "\t\t\t\tadi,channel-divider = <2>;\n"
            "\t\t\t\tadi,signal-source = <2>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c8: channel@8 {\n"
            "\t\t\t\treg = <8>;\n"
            '\t\t\t\tadi,extended-name = "ADC_SYSREF";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            "\t\t\t\tadi,channel-divider = <1>;\n"
            "\t\t\t\tadi,signal-source = <2>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c9: channel@9 {\n"
            "\t\t\t\treg = <9>;\n"
            '\t\t\t\tadi,extended-name = "ADC_CLK_FMC";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            f"\t\t\t\tadi,channel-divider = <2>; // {self._fmt_hz(_m1 // 2)}\n"
            "\t\t\t\tadi,signal-source = <0>;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c13: channel@13 {\n"
            "\t\t\t\treg = <13>;\n"
            '\t\t\t\tadi,extended-name = "ADC_CLK";\n'
            "\t\t\t\tadi,driver-mode = <3>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            f"\t\t\t\tadi,channel-divider = <1>; // {self._fmt_hz(_m1 // 1)}\n"
            "\t\t\t\tadi,signal-source = <0>;\n"
            "\t\t\t};\n"
        )

    def _make_jinja_env(self) -> Environment:
        """Create and return a Jinja2 Environment pointed at the XSA template directory."""
        from .exceptions import XsaParseError

        loc = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "..", "templates", "xsa"
        )
        if not os.path.isdir(loc):
            raise XsaParseError(f"template directory not found: {loc}")
        return Environment(loader=FileSystemLoader(loc))

    @cached_property
    def _env(self) -> "Environment":
        """Cached Jinja2 environment for the XSA template directory."""
        return self._make_jinja_env()

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

    @staticmethod
    def _fmt_gpi_gpo(controls: list) -> str:
        """Format a list of int/hex values as a space-separated hex string for DTS."""
        return " ".join(f"0x{int(v):02X}" for v in controls)

    def _build_hmc7044_channel_ctx(self, pll2_hz: int, channels_spec: list) -> list:
        """Pre-compute freq_str for each HMC7044 channel using _fmt_hz."""
        result = []
        for ch in channels_spec:
            d = dict(ch)
            if "freq_str" not in d:
                d["freq_str"] = self._fmt_hz(pll2_hz / d["divider"])
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
        clock_output_names: list,
        channels: list[dict] | None,
        raw_channels: str | None = None,
        *,
        jesd204_sysref_provider: bool = True,
        jesd204_max_sysref_hz: int = 2000000,
        pll1_loop_bandwidth_hz=None,
        pll1_ref_prio_ctrl=None,
        pll1_ref_autorevert: bool = False,
        pll1_charge_pump_ua=None,
        pfd1_max_freq_hz=None,
        sysref_timer_divider=None,
        pulse_generator_mode=None,
        clkin0_buffer_mode=None,
        clkin1_buffer_mode=None,
        oscin_buffer_mode=None,
        gpi_controls=None,
        gpo_controls=None,
        sync_pin_mode=None,
        high_perf_mode_dist_enable: bool = False,
    ) -> dict:
        """Build the context dict for hmc7044.tmpl."""
        clock_output_names_str = ", ".join(f'"{n}"' for n in clock_output_names)
        return {
            "label": label,
            "cs": cs,
            "spi_max_hz": spi_max_hz,
            "pll1_clkin_frequencies": pll1_clkin_frequencies,
            "vcxo_hz": vcxo_hz,
            "pll2_output_hz": pll2_output_hz,
            "clock_output_names_str": clock_output_names_str,
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
            "jesd_link_ids": [0],
            "jesd204_inputs": f"{ad.dac_core_label} 0 {ad.dac_jesd_link_id}",
        }

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
            "gpio_lines": [],
            "channels": channels,
        }

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
            # offset 1: fmcdaq2 ad9144 device references TPL core at offset 1 (line 415)
            "jesd204_inputs": f"{fmc.dac_core_label} 1 {fmc.dac_jesd_link_id}",
            "gpio_lines": gpio_lines,
        }

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
                "clock_output_names_str": '"adc_gt_clk", "rx_out_clk"',
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
            "clock_output_names_str": '"dac_gt_clk", "tx_out_clk"',
            "use_lpm_enable": True,
            "jesd_l": fmc.tx_l,
            "jesd_m": fmc.tx_m,
            "jesd_s": fmc.tx_s,
            "jesd204_inputs": None,
            "is_rx": False,
        }

    def _build_jesd204_overlay_ctx(
        self,
        fmc: "_FMCDAQ2Cfg",
        direction: str,
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> dict:
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
            "f": f,
            "k": k,
            "jesd204_inputs": jesd204_inputs,
            "converter_resolution": converter_resolution,
            "converters_per_device": converters_per_device,
            "bits_per_sample": bits_per_sample,
            "control_bits_per_sample": control_bits_per_sample,
        }

    def _build_clock_map(self, topology: XsaTopology) -> dict[str, ClkgenInstance]:
        """Return a mapping of output clock net name -> ClkgenInstance for fast clock resolution."""
        return {net: cg for cg in topology.clkgens for net in cg.output_clks}

    def _resolve_clock(
        self,
        inst: Jesd204Instance,
        clock_map: dict[str, ClkgenInstance],
        cfg: dict[str, Any],
        direction: str,
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> tuple[str, str, int]:
        """Resolve the clkgen label, device-clock label, and device-clock index for a JESD instance.

        Returns:
            ``(clkgen_label, device_clk_label, device_clk_index)``
        """
        clkgen = clock_map.get(inst.link_clk)
        unresolved_clk = clkgen is None
        if unresolved_clk:
            warnings.warn(
                f"unresolved clock net '{inst.link_clk}' for {inst.name}; "
                "using literal net name as clock label",
                UserWarning,
                stacklevel=3,
            )
            clkgen_label = inst.link_clk
        else:
            clkgen_label = clkgen.name.replace("-", "_")

        clock_cfg = cfg.get("clock", {})
        device_clk_label = clock_cfg.get(f"{direction}_device_clk_label", "hmc7044")
        if device_clk_label == "clkgen":
            if unresolved_clk:
                # External clock nets from HWH are not valid DTS labels.
                # Fall back to a known PS clock phandle to keep DTS valid.
                return (clkgen_label, ps_clk_label, ps_clk_index)
            device_clk_label = clkgen_label

        if device_clk_label == "hmc7044":
            device_clk_index = clock_cfg.get(f"hmc7044_{direction}_channel", 0)
        else:
            device_clk_index = clock_cfg.get(f"{direction}_device_clk_index", 0)

        return (clkgen_label, device_clk_label, device_clk_index)

    def _resolve_jesd_input(
        self,
        inst: Jesd204Instance,
        cfg: dict[str, Any],
        direction: str,
        clkgen_label: str,
    ) -> tuple[str, int]:
        """Resolve the ``jesd204-inputs`` phandle label and link-id for a JESD instance.

        Returns:
            ``(jesd_input_label, link_id)``
        """
        clock_cfg = cfg.get("clock", {})
        override_label = clock_cfg.get(f"{direction}_jesd_input_label")
        if override_label:
            return (
                override_label,
                int(clock_cfg.get(f"{direction}_jesd_input_link_id", 0)),
            )

        name = inst.name.replace("-", "_")
        if "_jesd_rx_axi" in name:
            guessed = name.replace("_jesd_rx_axi", "_xcvr")
        elif "_jesd_tx_axi" in name:
            guessed = name.replace("_jesd_tx_axi", "_xcvr")
        elif "_rx_os_jesd" in name:
            guessed = name.replace("_rx_os_jesd", "_rx_os_xcvr")
        elif "_rx_jesd" in name:
            guessed = name.replace("_rx_jesd", "_rx_xcvr")
        elif "_tx_jesd" in name:
            guessed = name.replace("_tx_jesd", "_tx_xcvr")
        else:
            guessed = clkgen_label
        return (guessed, int(clock_cfg.get(f"{direction}_jesd_input_link_id", 0)))

    def _render_jesd(
        self,
        inst: Jesd204Instance,
        jesd_params: dict[str, Any],
        clkgen_label: str,
        device_clk_label: str,
        device_clk_index: int,
        jesd_input_label: str,
        jesd_input_link_id: int,
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> str:
        """Render the ``jesd204_fsm.tmpl`` template for *inst* and return the DTS node string."""
        from .exceptions import ConfigError

        for key in ("F", "K"):
            if key not in jesd_params:
                raise ConfigError(f"jesd.{inst.direction}.{key}")
        return self._render(
            "jesd204_fsm.tmpl",
            {
                "instance": inst,
                "jesd": jesd_params,
                "clkgen_label": clkgen_label,
                "device_clk_label": device_clk_label,
                "device_clk_index": device_clk_index,
                "jesd_input_label": jesd_input_label,
                "jesd_input_link_id": jesd_input_link_id,
                "ps_clk_label": ps_clk_label,
                "ps_clk_index": ps_clk_index,
            },
        )

    def _render_converter(
        self, conv: ConverterInstance, rx_label: str, tx_label: str
    ) -> str:
        """Render a per-IP-type Jinja2 template for *conv*; returns a comment stub if no template exists."""
        from jinja2 import TemplateNotFound

        try:
            self._env.get_template(f"{conv.ip_type}.tmpl")
        except TemplateNotFound:
            return f"\t/* {conv.name}: no template for {conv.ip_type} */"
        return self._render(
            f"{conv.ip_type}.tmpl",
            {
                "instance": conv,
                "rx_jesd_label": rx_label,
                "tx_jesd_label": tx_label,
                "spi_label": "spi0",
                "spi_cs": conv.spi_cs if conv.spi_cs is not None else 0,
            },
        )

    def _render_clkgen(
        self,
        inst: ClkgenInstance,
        ps_clk_label: str,
        ps_clk_index: int,
    ) -> str:
        """Render the ``clkgen.tmpl`` template for *inst* and return the DTS node string."""
        return self._render(
            "clkgen.tmpl",
            {
                "instance": inst,
                "ps_clk_label": ps_clk_label,
                "ps_clk_index": ps_clk_index,
            },
        )

    @staticmethod
    def _platform_ps_labels(topology: XsaTopology) -> tuple[str, int, str]:
        """Return ``(ps_clk_label, ps_clk_index, gpio_label)`` appropriate for the topology's platform."""
        if topology.inferred_platform() == "zc706":
            return ("clkc", 15, "gpio0")
        return ("zynqmp_clk", 71, "gpio")

    @staticmethod
    def _format_nested_block(block: str, prefix: str = "\t\t\t") -> str:
        """Re-indent each line of *block* with *prefix* and return the result."""
        lines = block.strip("\n").splitlines()
        if not lines:
            return ""
        return "".join(f"{prefix}{line.lstrip()}\n" for line in lines)

    @staticmethod
    def _ad9081_converter_select(rx_m: int, rx_link_mode: int) -> str:
        """Return the ``adi,converter-select`` phandle list string for the AD9081 RX path."""
        # M4/L8 (mode 18) follows the upstream ADI mapping used by the
        # zynqmp-zcu102-rev10-ad9081 reference design.
        if rx_link_mode == 18 and rx_m == 4:
            return (
                "<&ad9081_rx_fddc_chan0 0>, <&ad9081_rx_fddc_chan0 1>, "
                "<&ad9081_rx_fddc_chan1 0>, <&ad9081_rx_fddc_chan1 1>"
            )
        # For M=8 keep the existing IQ-pair mapping used by the reference flow.
        if rx_m >= 8:
            return (
                "<&ad9081_rx_fddc_chan0 0>, <&ad9081_rx_fddc_chan0 1>, "
                "<&ad9081_rx_fddc_chan1 0>, <&ad9081_rx_fddc_chan1 1>, "
                "<&ad9081_rx_fddc_chan2 0>, <&ad9081_rx_fddc_chan2 1>, "
                "<&ad9081_rx_fddc_chan3 0>, <&ad9081_rx_fddc_chan3 1>"
            )
        # For reduced-M modes (e.g. M=4), map one converter per channel.
        return ", ".join(
            f"<&ad9081_rx_fddc_chan{i} 0>" for i in range(max(1, min(rx_m, 8)))
        )

    @staticmethod
    def _ad9081_tx_converter_select(tx_m: int, tx_link_mode: int) -> str:
        """Return the ``adi,converter-select`` phandle list string for the AD9081 TX path."""
        # M4/L8 (mode 17) follows the upstream ADI mapping used by the
        # zynqmp-zcu102-rev10-ad9081 reference design.
        if tx_link_mode == 17 and tx_m == 4:
            return (
                "<&ad9081_tx_fddc_chan0 0>, <&ad9081_tx_fddc_chan0 1>, "
                "<&ad9081_tx_fddc_chan1 0>, <&ad9081_tx_fddc_chan1 1>"
            )
        if tx_m >= 8:
            return (
                "<&ad9081_tx_fddc_chan0 0>, <&ad9081_tx_fddc_chan0 1>, "
                "<&ad9081_tx_fddc_chan1 0>, <&ad9081_tx_fddc_chan1 1>, "
                "<&ad9081_tx_fddc_chan2 0>, <&ad9081_tx_fddc_chan2 1>, "
                "<&ad9081_tx_fddc_chan3 0>, <&ad9081_tx_fddc_chan3 1>"
            )
        return ", ".join(
            f"<&ad9081_tx_fddc_chan{i} 0>" for i in range(max(1, min(tx_m, 8)))
        )

    @staticmethod
    def _ad9081_lane_map(lanes: int) -> str:
        """Return a space-separated 8-element lane-mapping string padded with 7 for unused lanes."""
        lane_count = max(1, min(lanes, 8))
        values = list(range(lane_count)) + [7] * (8 - lane_count)
        return " ".join(str(v) for v in values)

    @staticmethod
    def _ad9081_lane_map_for_mode(direction: str, lanes: int, link_mode: int) -> str:
        """Return the board-specific ``adi,logical-lane-mapping`` string for the given AD9081 link mode.

        Falls back to the generic sequential lane map when no known-good mapping exists.
        """
        # Board-specific known-good mappings from upstream ADI DTS.
        if direction == "tx" and link_mode == 17 and lanes == 8:
            return "0 2 7 6 1 5 4 3"
        if direction == "rx" and link_mode == 18 and lanes == 8:
            return "2 0 7 6 5 4 3 1"
        if direction == "tx" and link_mode == 9 and lanes == 4:
            return "0 2 7 7 1 7 7 3"
        if direction == "rx" and link_mode == 10 and lanes == 4:
            return "2 0 7 7 7 7 3 1"
        return NodeBuilder._ad9081_lane_map(lanes)

    def _resolve_ad9081_link_mode(
        self,
        ad9081_cfg: dict[str, Any],
        jesd_cfg: dict[str, Any],
        direction: str,
    ) -> int:
        """Determine the AD9081 link mode for *direction* from config or by inferring from M and L values.

        Raises ConfigError if the mode cannot be determined.
        """
        from .exceptions import ConfigError

        explicit = ad9081_cfg.get(f"{direction}_link_mode")
        if explicit is not None:
            return int(explicit)

        alt_explicit = jesd_cfg.get(direction, {}).get("mode")
        if alt_explicit is not None:
            return int(alt_explicit)

        m = int(jesd_cfg.get(direction, {}).get("M", 0))
        lanes = int(jesd_cfg.get(direction, {}).get("L", 0))
        modes = self._AD9081_LINK_MODE_BY_ML.get((m, lanes))
        if modes is None:
            raise ConfigError(
                f"ad9081.{direction}_link_mode (missing and could not infer for M={m}, L={lanes})"
            )
        return modes[0] if direction == "rx" else modes[1]

    def _build_ad9081_nodes(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int,
        gpio_label: str,
    ) -> list[str]:
        """Build DTS node strings for an AD9081 MxFE design with HMC7044 clock chip.

        Returns an empty list if the topology does not contain an ``axi_ad9081`` converter
        with MXFE JESD instances.
        """
        has_ad9081 = any(c.ip_type == "axi_ad9081" for c in topology.converters)
        if not has_ad9081:
            return []

        labels = self._topology_instance_names(topology)
        if not any("mxfe" in lbl for lbl in labels):
            return []

        clock_cfg = cfg.get("clock", {})
        rx_chan = int(clock_cfg.get("hmc7044_rx_channel", 10))
        tx_chan = int(clock_cfg.get("hmc7044_tx_channel", 6))
        jesd_cfg = cfg.get("jesd", {})
        rx_cfg = jesd_cfg.get("rx", {})
        tx_cfg = jesd_cfg.get("tx", {})
        rx_f = int(rx_cfg.get("F", 4))
        rx_k = int(rx_cfg.get("K", 32))
        rx_m = int(rx_cfg.get("M", 8))
        rx_l = int(rx_cfg.get("L", 4))
        rx_s = int(rx_cfg.get("S", 1))
        tx_f = int(tx_cfg.get("F", 4))
        tx_k = int(tx_cfg.get("K", 32))
        tx_m = int(tx_cfg.get("M", 8))
        tx_l = int(tx_cfg.get("L", 4))
        tx_s = int(tx_cfg.get("S", 1))
        ad9081_cfg = cfg.get("ad9081", {})
        ad9081_board_cfg = cfg.get("ad9081_board", {})
        rx_link_mode = self._resolve_ad9081_link_mode(ad9081_cfg, jesd_cfg, "rx")
        tx_link_mode = self._resolve_ad9081_link_mode(ad9081_cfg, jesd_cfg, "tx")
        adc_frequency_hz = int(ad9081_cfg.get("adc_frequency_hz", 4000000000))
        dac_frequency_hz = int(ad9081_cfg.get("dac_frequency_hz", 12000000000))
        rx_cddc_decimation = int(ad9081_cfg.get("rx_cddc_decimation", 4))
        rx_fddc_decimation = int(ad9081_cfg.get("rx_fddc_decimation", 4))
        tx_cduc_interpolation = int(ad9081_cfg.get("tx_cduc_interpolation", 8))
        tx_fduc_interpolation = int(ad9081_cfg.get("tx_fduc_interpolation", 6))
        rx_sys_clk_select = int(ad9081_cfg.get("rx_sys_clk_select", 3))
        tx_sys_clk_select = int(ad9081_cfg.get("tx_sys_clk_select", 3))
        rx_out_clk_select = int(ad9081_cfg.get("rx_out_clk_select", 4))
        tx_out_clk_select = int(ad9081_cfg.get("tx_out_clk_select", 4))
        rx_link_id = int(ad9081_cfg.get("rx_link_id", 2))
        tx_link_id = int(ad9081_cfg.get("tx_link_id", 0))
        rx_converter_select = self._ad9081_converter_select(rx_m, rx_link_mode)
        tx_converter_select = self._ad9081_tx_converter_select(tx_m, tx_link_mode)
        rx_lane_map = self._ad9081_lane_map_for_mode("rx", rx_l, rx_link_mode)
        tx_lane_map = self._ad9081_lane_map_for_mode("tx", tx_l, tx_link_mode)
        clock_spi = str(ad9081_board_cfg.get("clock_spi", "spi1"))
        clock_cs = int(ad9081_board_cfg.get("clock_cs", 0))
        adc_spi = str(ad9081_board_cfg.get("adc_spi", "spi0"))
        adc_cs = int(ad9081_board_cfg.get("adc_cs", 0))
        reset_gpio = int(ad9081_board_cfg.get("reset_gpio", 133))
        sysref_req_gpio = int(ad9081_board_cfg.get("sysref_req_gpio", 121))
        rx2_enable_gpio = int(ad9081_board_cfg.get("rx2_enable_gpio", 135))
        rx1_enable_gpio = int(ad9081_board_cfg.get("rx1_enable_gpio", 134))
        tx2_enable_gpio = int(ad9081_board_cfg.get("tx2_enable_gpio", 137))
        tx1_enable_gpio = int(ad9081_board_cfg.get("tx1_enable_gpio", 136))
        # PLL2 output frequency: adi,pll2-output-frequency = <3000000000>
        _pll2 = 3_000_000_000
        default_hmc7044_channels_block = (
            "\t\t\thmc7044_c0: channel@0 {\n"
            "\t\t\t\treg = <0>;\n"
            '\t\t\t\tadi,extended-name = "CORE_CLK_RX";\n'
            f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(_pll2 // 12)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c2: channel@2 {\n"
            "\t\t\t\treg = <2>;\n"
            '\t\t\t\tadi,extended-name = "DEV_REFCLK";\n'
            f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(_pll2 // 12)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c3: channel@3 {\n"
            "\t\t\t\treg = <3>;\n"
            '\t\t\t\tadi,extended-name = "DEV_SYSREF";\n'
            f"\t\t\t\tadi,divider = <1536>; // {self._fmt_hz(_pll2 // 1536)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c6: channel@6 {\n"
            "\t\t\t\treg = <6>;\n"
            '\t\t\t\tadi,extended-name = "CORE_CLK_TX";\n'
            f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(_pll2 // 12)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c8: channel@8 {\n"
            "\t\t\t\treg = <8>;\n"
            '\t\t\t\tadi,extended-name = "FPGA_REFCLK1";\n'
            f"\t\t\t\tadi,divider = <6>; // {self._fmt_hz(_pll2 // 6)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c10: channel@10 {\n"
            "\t\t\t\treg = <10>;\n"
            '\t\t\t\tadi,extended-name = "CORE_CLK_RX_ALT";\n'
            f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(_pll2 // 12)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c12: channel@12 {\n"
            "\t\t\t\treg = <12>;\n"
            '\t\t\t\tadi,extended-name = "FPGA_REFCLK2";\n'
            f"\t\t\t\tadi,divider = <6>; // {self._fmt_hz(_pll2 // 6)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t};\n"
            "\t\t\thmc7044_c13: channel@13 {\n"
            "\t\t\t\treg = <13>;\n"
            '\t\t\t\tadi,extended-name = "FPGA_SYSREF";\n'
            f"\t\t\t\tadi,divider = <1536>; // {self._fmt_hz(_pll2 // 1536)}\n"
            "\t\t\t\tadi,driver-mode = <2>;\n"
            "\t\t\t\tadi,jesd204-sysref-chan;\n"
            "\t\t\t};\n"
        )
        custom_hmc7044_blocks = ad9081_board_cfg.get("hmc7044_channel_blocks")
        if custom_hmc7044_blocks:
            hmc7044_channels_block = "".join(
                self._format_nested_block(str(block)) for block in custom_hmc7044_blocks
            )
        else:
            hmc7044_channels_block = default_hmc7044_channels_block

        nodes = [
            "\t&axi_mxfe_rx_dma {\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            "\t&axi_mxfe_tx_dma {\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            "\t&axi_mxfe_rx_xcvr {\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            "\t\tclocks = <&hmc7044 12>;\n"
            '\t\tclock-names = "conv";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_gt_clk", "rx_out_clk";\n'
            f"\t\tadi,sys-clk-select = <{rx_sys_clk_select}>;\n"
            f"\t\tadi,out-clk-select = <{rx_out_clk_select}>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&hmc7044 0 {rx_link_id}>;\n"
            "\t};",
            "\t&axi_mxfe_tx_xcvr {\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            "\t\tclocks = <&hmc7044 12>;\n"
            '\t\tclock-names = "conv";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "tx_gt_clk", "tx_out_clk";\n'
            f"\t\tadi,sys-clk-select = <{tx_sys_clk_select}>;\n"
            f"\t\tadi,out-clk-select = <{tx_out_clk_select}>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\tjesd204-inputs = <&hmc7044 0 0>;\n"
            "\t};",
            "\t&rx_mxfe_tpl_core_adc_tpl_core {\n"
            '\t\tcompatible = "adi,axi-ad9081-rx-1.0";\n'
            "\t\tdmas = <&axi_mxfe_rx_dma 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t\tspibus-connected = <&trx0_ad9081>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tjesd204-inputs = <&axi_mxfe_rx_jesd_rx_axi 0 {rx_link_id}>;\n"
            "\t};",
            "\t&tx_mxfe_tpl_core_dac_tpl_core {\n"
            '\t\tcompatible = "adi,axi-ad9081-tx-1.0";\n'
            "\t\tdmas = <&axi_mxfe_tx_dma 0>;\n"
            '\t\tdma-names = "tx";\n'
            "\t\tclocks = <&trx0_ad9081 1>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t\tspibus-connected = <&trx0_ad9081>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\tjesd204-inputs = <&axi_mxfe_tx_jesd_tx_axi 0 0>;\n"
            "\t};",
            f"\t&{clock_spi} {{\n"
            '\t\tstatus = "okay";\n'
            f"\t\thmc7044: hmc7044@{clock_cs} {{\n"
            '\t\t\tcompatible = "adi,hmc7044";\n'
            f"\t\t\treg = <{clock_cs}>;\n"
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            "\t\t\t#clock-cells = <1>;\n"
            "\t\t\tspi-max-frequency = <1000000>;\n"
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-sysref-provider;\n"
            "\t\t\tadi,jesd204-max-sysref-frequency-hz = <2000000>;\n"
            "\t\t\tadi,pll1-clkin-frequencies = <122880000 10000000 0 0>;\n"
            "\t\t\tadi,pll1-ref-prio-ctrl = <0xE1>;\n"
            "\t\t\tadi,pll1-ref-autorevert-enable;\n"
            "\t\t\tadi,vcxo-frequency = <122880000>;\n"
            "\t\t\tadi,pll1-loop-bandwidth-hz = <200>;\n"
            "\t\t\tadi,pll1-charge-pump-current-ua = <720>;\n"
            "\t\t\tadi,pfd1-maximum-limit-frequency-hz = <1000000>;\n"
            "\t\t\tadi,pll2-output-frequency = <3000000000>;\n"
            "\t\t\tadi,sysref-timer-divider = <1024>;\n"
            "\t\t\tadi,pulse-generator-mode = <0>;\n"
            "\t\t\tadi,clkin0-buffer-mode = <0x07>;\n"
            "\t\t\tadi,clkin1-buffer-mode = <0x07>;\n"
            "\t\t\tadi,oscin-buffer-mode = <0x15>;\n"
            "\t\t\tadi,gpi-controls = <0x00 0x00 0x00 0x00>;\n"
            "\t\t\tadi,gpo-controls = <0x37 0x33 0x00 0x00>;\n"
            '\t\t\tclock-output-names = "hmc7044_out0", "hmc7044_out1", "hmc7044_out2", '
            '"hmc7044_out3", "hmc7044_out4", "hmc7044_out5", '
            '"hmc7044_out6", "hmc7044_out7", "hmc7044_out8", '
            '"hmc7044_out9", "hmc7044_out10", "hmc7044_out11", '
            '"hmc7044_out12", "hmc7044_out13";\n'
            f"{hmc7044_channels_block}"
            "\t\t};\n"
            "\t};",
            f"\t&{adc_spi} {{\n"
            '\t\tstatus = "okay";\n'
            f"\t\ttrx0_ad9081: ad9081@{adc_cs} {{\n"
            '\t\t\tcompatible = "adi,ad9081";\n'
            f"\t\t\treg = <{adc_cs}>;\n"
            "\t\t\tspi-max-frequency = <5000000>;\n"
            f"\t\t\treset-gpios = <&{gpio_label} {reset_gpio} 0>;\n"
            f"\t\t\tsysref-req-gpios = <&{gpio_label} {sysref_req_gpio} 0>;\n"
            f"\t\t\trx2-enable-gpios = <&{gpio_label} {rx2_enable_gpio} 0>;\n"
            f"\t\t\trx1-enable-gpios = <&{gpio_label} {rx1_enable_gpio} 0>;\n"
            f"\t\t\ttx2-enable-gpios = <&{gpio_label} {tx2_enable_gpio} 0>;\n"
            f"\t\t\ttx1-enable-gpios = <&{gpio_label} {tx1_enable_gpio} 0>;\n"
            "\t\t\tclocks = <&hmc7044 2>;\n"
            '\t\t\tclock-names = "dev_clk";\n'
            "\t\t\t#clock-cells = <1>;\n"
            '\t\t\tclock-output-names = "rx_sampl_clk", "tx_sampl_clk";\n'
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <0>;\n"
            f"\t\t\tjesd204-link-ids = <{rx_link_id} {tx_link_id}>;\n"
            f"\t\t\tjesd204-inputs = <&rx_mxfe_tpl_core_adc_tpl_core 0 {rx_link_id}>, <&tx_mxfe_tpl_core_dac_tpl_core 0 {tx_link_id}>;\n"
            "\t\t\tadi,tx-dacs {\n"
            "\t\t\t\t#size-cells = <0>;\n"
            "\t\t\t\t#address-cells = <1>;\n"
            f"\t\t\t\tadi,dac-frequency-hz = /bits/ 64 <{dac_frequency_hz}>;\n"
            "\t\t\t\tadi,main-data-paths {\n"
            "\t\t\t\t\t#address-cells = <1>;\n"
            "\t\t\t\t\t#size-cells = <0>;\n"
            f"\t\t\t\t\tadi,interpolation = <{tx_cduc_interpolation}>;\n"
            "\t\t\t\t\tdac@0 { reg = <0>; };\n"
            "\t\t\t\t\tdac@1 { reg = <1>; };\n"
            "\t\t\t\t\tdac@2 { reg = <2>; };\n"
            "\t\t\t\t\tdac@3 { reg = <3>; };\n"
            "\t\t\t\t};\n"
            "\t\t\t\tadi,channelizer-paths {\n"
            "\t\t\t\t\t#address-cells = <1>;\n"
            "\t\t\t\t\t#size-cells = <0>;\n"
            f"\t\t\t\t\tadi,interpolation = <{tx_fduc_interpolation}>;\n"
            "\t\t\t\t\tad9081_tx_fddc_chan0: channel@0 { reg = <0>; };\n"
            "\t\t\t\t\tad9081_tx_fddc_chan1: channel@1 { reg = <1>; };\n"
            "\t\t\t\t\tad9081_tx_fddc_chan2: channel@2 { reg = <2>; };\n"
            "\t\t\t\t\tad9081_tx_fddc_chan3: channel@3 { reg = <3>; };\n"
            "\t\t\t\t\tad9081_tx_fddc_chan4: channel@4 { reg = <4>; };\n"
            "\t\t\t\t\tad9081_tx_fddc_chan5: channel@5 { reg = <5>; };\n"
            "\t\t\t\t\tad9081_tx_fddc_chan6: channel@6 { reg = <6>; };\n"
            "\t\t\t\t\tad9081_tx_fddc_chan7: channel@7 { reg = <7>; };\n"
            "\t\t\t\t};\n"
            "\t\t\t\tadi,jesd-links {\n"
            "\t\t\t\t\t#size-cells = <0>;\n"
            "\t\t\t\t\t#address-cells = <1>;\n"
            "\t\t\t\t\tlink@0 {\n"
            "\t\t\t\t\t\treg = <0>;\n"
            f"\t\t\t\t\t\tadi,converter-select = {tx_converter_select};\n"
            f"\t\t\t\t\t\tadi,logical-lane-mapping = /bits/ 8 <{tx_lane_map}>;\n"
            f"\t\t\t\t\t\tadi,link-mode = <{tx_link_mode}>;\n"
            "\t\t\t\t\t\tadi,subclass = <1>;\n"
            "\t\t\t\t\t\tadi,version = <1>;\n"
            "\t\t\t\t\t\tadi,dual-link = <0>;\n"
            f"\t\t\t\t\t\tadi,converters-per-device = <{tx_m}>;\n"
            "\t\t\t\t\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\t\t\t\t\tadi,octets-per-frame = <{tx_f}>;\n"
            "\t\t\t\t\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\t\t\t\t\tadi,frames-per-multiframe = <{tx_k}>;\n"
            "\t\t\t\t\t\tadi,converter-resolution = <16>;\n"
            "\t\t\t\t\t\tadi,bits-per-sample = <16>;\n"
            "\t\t\t\t\t\tadi,control-bits-per-sample = <0>;\n"
            f"\t\t\t\t\t\tadi,lanes-per-device = <{tx_l}>;\n"
            f"\t\t\t\t\t\tadi,samples-per-converter-per-frame = <{tx_s}>;\n"
            "\t\t\t\t\t\tadi,high-density = <0>;\n"
            "\t\t\t\t\t};\n"
            "\t\t\t\t};\n"
            "\t\t\t};\n"
            "\t\t\tadi,rx-adcs {\n"
            "\t\t\t\t#size-cells = <0>;\n"
            "\t\t\t\t#address-cells = <1>;\n"
            f"\t\t\t\tadi,adc-frequency-hz = /bits/ 64 <{adc_frequency_hz}>;\n"
            "\t\t\t\tadi,main-data-paths {\n"
            "\t\t\t\t\t#address-cells = <1>;\n"
            "\t\t\t\t\t#size-cells = <0>;\n"
            f"\t\t\t\t\tadc@0 {{ reg = <0>; adi,decimation = <{rx_cddc_decimation}>; }};\n"
            f"\t\t\t\t\tadc@1 {{ reg = <1>; adi,decimation = <{rx_cddc_decimation}>; }};\n"
            f"\t\t\t\t\tadc@2 {{ reg = <2>; adi,decimation = <{rx_cddc_decimation}>; }};\n"
            f"\t\t\t\t\tadc@3 {{ reg = <3>; adi,decimation = <{rx_cddc_decimation}>; }};\n"
            "\t\t\t\t};\n"
            "\t\t\t\tadi,channelizer-paths {\n"
            "\t\t\t\t\t#address-cells = <1>;\n"
            "\t\t\t\t\t#size-cells = <0>;\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan0: channel@0 {{ reg = <0>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan1: channel@1 {{ reg = <1>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan2: channel@2 {{ reg = <2>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan3: channel@3 {{ reg = <3>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan4: channel@4 {{ reg = <4>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan5: channel@5 {{ reg = <5>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan6: channel@6 {{ reg = <6>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            f"\t\t\t\t\tad9081_rx_fddc_chan7: channel@7 {{ reg = <7>; adi,decimation = <{rx_fddc_decimation}>; }};\n"
            "\t\t\t\t};\n"
            "\t\t\t\tadi,jesd-links {\n"
            "\t\t\t\t\t#size-cells = <0>;\n"
            "\t\t\t\t\t#address-cells = <1>;\n"
            "\t\t\t\t\tlink@0 {\n"
            "\t\t\t\t\t\treg = <0>;\n"
            f"\t\t\t\t\t\tadi,converter-select = {rx_converter_select};\n"
            f"\t\t\t\t\t\tadi,logical-lane-mapping = /bits/ 8 <{rx_lane_map}>;\n"
            f"\t\t\t\t\t\tadi,link-mode = <{rx_link_mode}>;\n"
            "\t\t\t\t\t\tadi,subclass = <1>;\n"
            "\t\t\t\t\t\tadi,version = <1>;\n"
            "\t\t\t\t\t\tadi,dual-link = <0>;\n"
            f"\t\t\t\t\t\tadi,converters-per-device = <{rx_m}>;\n"
            "\t\t\t\t\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\t\t\t\t\tadi,octets-per-frame = <{rx_f}>;\n"
            "\t\t\t\t\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\t\t\t\t\tadi,frames-per-multiframe = <{rx_k}>;\n"
            "\t\t\t\t\t\tadi,converter-resolution = <16>;\n"
            "\t\t\t\t\t\tadi,bits-per-sample = <16>;\n"
            "\t\t\t\t\t\tadi,control-bits-per-sample = <0>;\n"
            f"\t\t\t\t\t\tadi,lanes-per-device = <{rx_l}>;\n"
            f"\t\t\t\t\t\tadi,samples-per-converter-per-frame = <{rx_s}>;\n"
            "\t\t\t\t\t\tadi,high-density = <0>;\n"
            "\t\t\t\t\t};\n"
            "\t\t\t\t};\n"
            "\t\t\t};\n"
            "\t\t};\n"
            "\t};",
        ]

        for jesd in topology.jesd204_rx:
            lbl = jesd.name.replace("-", "_")
            if "mxfe" not in lbl:
                continue
            nodes.append(
                f"\t&{lbl} {{\n"
                '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
                f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, <&hmc7044 {rx_chan}>, <&axi_mxfe_rx_xcvr 0>;\n"
                '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
                "\t\t#clock-cells = <0>;\n"
                "\t\tjesd204-device;\n"
                "\t\t#jesd204-cells = <2>;\n"
                "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
                f"\t\tadi,octets-per-frame = <{rx_f}>;\n"
                "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
                f"\t\tadi,frames-per-multiframe = <{rx_k}>;\n"
                f"\t\tjesd204-inputs = <&axi_mxfe_rx_xcvr 0 {rx_link_id}>;\n"
                "\t};"
            )
        for jesd in topology.jesd204_tx:
            lbl = jesd.name.replace("-", "_")
            if "mxfe" not in lbl:
                continue
            nodes.append(
                f"\t&{lbl} {{\n"
                '\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n'
                f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, <&hmc7044 {tx_chan}>, <&axi_mxfe_tx_xcvr 0>;\n"
                '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
                "\t\t#clock-cells = <0>;\n"
                "\t\tjesd204-device;\n"
                "\t\t#jesd204-cells = <2>;\n"
                "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
                f"\t\tadi,octets-per-frame = <{tx_f}>;\n"
                "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
                f"\t\tadi,frames-per-multiframe = <{tx_k}>;\n"
                f"\t\tjesd204-inputs = <&axi_mxfe_tx_xcvr 0 {tx_link_id}>;\n"
                "\t};"
            )

        return nodes

    def _build_adrv9009_nodes(
        self, topology: XsaTopology, cfg: dict[str, Any]
    ) -> list[str]:
        """Build DTS node strings for an ADRV9009/9025 transceiver design.

        Handles both standard single-chip and dual-chip FMComms8 layouts.
        Returns an empty list if no ADRV90xx instances are found in the topology.
        """
        board_cfg = cfg.get("adrv9009_board", {})
        platform = topology.inferred_platform()
        if platform == "zc706":
            ps_clk_label = "clkc"
            ps_clk_index = 15
            gpio_label = "gpio0"
        else:
            ps_clk_label = "zynqmp_clk"
            ps_clk_index = 71
            gpio_label = "gpio"
        labels = self._topology_instance_names(topology)
        is_fmcomms8_layout = self._is_fmcomms8_layout(labels)
        if not any(self._is_adrv90xx_name(lbl) for lbl in labels):
            return []
        is_adrv9025_family = any(
            "adrv9025" in lbl.lower() or "adrv9026" in lbl.lower() for lbl in labels
        )
        phy_family = "adrv9025" if is_adrv9025_family else "adrv9009"
        phy_label = f"trx0_{phy_family}"
        phy_node_name = f"{phy_family}-phy"
        phy_compatible = f'"adi,{phy_family}", "{phy_family}"'
        rx_jesd_label = next(
            (
                lbl
                for lbl in sorted(labels)
                if "_rx_jesd_rx_axi" in lbl and "_rx_os_" not in lbl
            ),
            next(
                (
                    lbl
                    for lbl in sorted(labels)
                    if "_rx_jesd" in lbl and "_rx_os_" not in lbl
                ),
                None,
            ),
        )
        rx_os_jesd_label = next(
            (lbl for lbl in sorted(labels) if "_rx_os_jesd_rx_axi" in lbl),
            next(
                (lbl for lbl in sorted(labels) if "_obs_jesd_rx_axi" in lbl),
                next(
                    (
                        lbl
                        for lbl in sorted(labels)
                        if "_rx_os_jesd" in lbl or "_obs_jesd" in lbl
                    ),
                    None,
                ),
            ),
        )
        tx_jesd_label = next(
            (lbl for lbl in sorted(labels) if "_tx_jesd_tx_axi" in lbl),
            next((lbl for lbl in sorted(labels) if "_tx_jesd" in lbl), None),
        )
        if not rx_jesd_label or not tx_jesd_label:
            return []

        rx_f = int(cfg.get("jesd", {}).get("rx", {}).get("F", 4))
        rx_k = int(cfg.get("jesd", {}).get("rx", {}).get("K", 32))
        tx_k = int(cfg.get("jesd", {}).get("tx", {}).get("K", 32))
        tx_m = int(cfg.get("jesd", {}).get("tx", {}).get("M", 4))

        rx_clkgen_label = rx_jesd_label.replace("_jesd_rx_axi", "_clkgen").replace(
            "_rx_jesd", "_rx_clkgen"
        )
        tx_clkgen_label = tx_jesd_label.replace("_jesd_tx_axi", "_clkgen").replace(
            "_tx_jesd", "_tx_clkgen"
        )

        rx_xcvr_label = rx_jesd_label.replace("_jesd_rx_axi", "_xcvr").replace(
            "_rx_jesd", "_rx_xcvr"
        )
        tx_xcvr_label = tx_jesd_label.replace("_jesd_tx_axi", "_xcvr").replace(
            "_tx_jesd", "_tx_xcvr"
        )
        # Standard ADRV9009 designs use derived clkgen instances.
        # FMComms8 drives converter clocks from explicit HMC7044 channels.
        has_rx_clkgen = not is_fmcomms8_layout
        has_tx_clkgen = not is_fmcomms8_layout
        if rx_os_jesd_label:
            rx_os_xcvr_label = rx_os_jesd_label.replace(
                "_jesd_rx_axi", "_xcvr"
            ).replace("_rx_os_jesd", "_rx_os_xcvr")
            rx_os_clkgen_label = rx_os_jesd_label.replace(
                "_jesd_rx_axi", "_clkgen"
            ).replace("_rx_os_jesd", "_rx_os_clkgen")
        else:
            rx_os_xcvr_label = "axi_adrv9009_rx_os_xcvr"
            rx_os_clkgen_label = "axi_adrv9009_rx_os_clkgen"

        has_rx_os_clkgen = bool(rx_os_jesd_label) and not is_fmcomms8_layout

        rx_core_label = "axi_adrv9009_core_rx"
        rx_os_core_label = "axi_adrv9009_core_rx_obs"
        tx_core_label = "axi_adrv9009_core_tx"
        if is_fmcomms8_layout:
            rx_core_label = self._pick_matching_label(
                labels,
                rx_core_label,
                ("adrv9009", "tpl_core", "rx", "adc"),
            )
            rx_os_core_label = self._pick_matching_label(
                labels,
                rx_os_core_label,
                ("adrv9009", "tpl_core", "obs", "adc"),
            )
            tx_core_label = self._pick_matching_label(
                labels,
                tx_core_label,
                ("adrv9009", "tpl_core", "tx", "dac"),
            )

        misc_clk_hz = int(board_cfg.get("misc_clk_hz", 245760000))
        spi_bus = str(board_cfg.get("spi_bus", "spi0"))
        clk_cs = int(board_cfg.get("clk_cs", 0))
        trx_cs = int(board_cfg.get("trx_cs", 1))
        trx_reset_gpio = int(board_cfg.get("trx_reset_gpio", 130))
        trx_sysref_req_gpio = int(board_cfg.get("trx_sysref_req_gpio", 136))
        trx_spi_max_frequency = int(board_cfg.get("trx_spi_max_frequency", 25000000))
        if is_fmcomms8_layout:
            phy_compatible = '"adrv9009-x2"'

        if is_fmcomms8_layout:
            clock_chip_label = "hmc7044_fmc"
            # Channel mapping from adi-fmcomms8.dtsi / zynqmp-zcu102-rev10-adrv9009-fmcomms8.dts:
            #  ch4 = JESD_REFCLK_TX_OBS (XCVR conv for TX+OBS), ch5 = JESD_REFCLK_RX (XCVR conv for RX)
            #  ch8 = CORE_CLK_TX_OBS (device_clk for TX+OBS JESD and div40), ch9 = CORE_CLK_RX (device_clk for RX JESD and div40)
            hmc7044_rx_channel = int(board_cfg.get("hmc7044_rx_channel", 9))
            hmc7044_tx_channel = int(board_cfg.get("hmc7044_tx_channel", 8))
            hmc7044_xcvr_channel = int(board_cfg.get("hmc7044_xcvr_channel", 5))
            hmc7044_tx_xcvr_channel = int(board_cfg.get("hmc7044_tx_xcvr_channel", 4))
            # Per-PHY device/sysref channels (dual-chip FMComms8 layout)
            # trx0 (C): dev=ch0, sysref_dev=ch1, sysref_fmc=ch6
            # trx1 (D): dev=ch2, sysref_dev=ch3, sysref_fmc=ch7
            hmc7044_trx0_dev_channel = int(board_cfg.get("hmc7044_trx0_dev_channel", 0))
            hmc7044_trx0_sysref_dev_channel = int(
                board_cfg.get("hmc7044_trx0_sysref_dev_channel", 1)
            )
            hmc7044_trx0_sysref_fmc_channel = int(
                board_cfg.get("hmc7044_trx0_sysref_fmc_channel", 6)
            )
            hmc7044_trx1_dev_channel = int(board_cfg.get("hmc7044_trx1_dev_channel", 2))
            hmc7044_trx1_sysref_dev_channel = int(
                board_cfg.get("hmc7044_trx1_sysref_dev_channel", 3)
            )
            hmc7044_trx1_sysref_fmc_channel = int(
                board_cfg.get("hmc7044_trx1_sysref_fmc_channel", 7)
            )
            trx2_cs = int(board_cfg.get("trx2_cs", trx_cs + 1))
            trx2_reset_gpio = int(board_cfg.get("trx2_reset_gpio", 135))
            hmc7044_pll1_clkin_freqs = board_cfg.get(
                "hmc7044_pll1_clkin_frequencies",
                [30720000, 30720000, 30720000, 19200000],
            )
            hmc7044_vcxo_freq = int(board_cfg.get("hmc7044_vcxo_frequency", 122880000))
            hmc7044_pll2_out_freq = int(
                board_cfg.get("hmc7044_pll2_output_frequency", 2949120000)
            )
            hmc7044_gpi_controls = board_cfg.get(
                "hmc7044_gpi_controls", [0x00, 0x00, 0x00, 0x11]
            )
            hmc7044_gpo_controls = board_cfg.get(
                "hmc7044_gpo_controls", [0x1F, 0x2B, 0x00, 0x00]
            )
            _pll1_freqs_str = " ".join(str(f) for f in hmc7044_pll1_clkin_freqs)
            _gpi_str = " ".join(f"0x{v:02X}" for v in hmc7044_gpi_controls)
            _gpo_str = " ".join(f"0x{v:02X}" for v in hmc7044_gpo_controls)
            default_clock_chip_channels_block = (
                "\t\t\thmc7044_fmc_c0: channel@0 {\n"
                "\t\t\t\treg = <0>;\n"
                '\t\t\t\tadi,extended-name = "DEV_REFCLK_C";\n'
                f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(hmc7044_pll2_out_freq // 12)}\n"
                "\t\t\t\tadi,driver-mode = <1>;\n"
                "\t\t\t\tadi,coarse-digital-delay = <15>;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c1: channel@1 {\n"
                "\t\t\t\treg = <1>;\n"
                '\t\t\t\tadi,extended-name = "DEV_SYSREF_C";\n'
                f"\t\t\t\tadi,divider = <3840>; // {self._fmt_hz(hmc7044_pll2_out_freq // 3840)}\n"
                "\t\t\t\tadi,driver-mode = <2>;\n"
                "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
                "\t\t\t\tadi,high-performance-mode-disable;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c2: channel@2 {\n"
                "\t\t\t\treg = <2>;\n"
                '\t\t\t\tadi,extended-name = "DEV_REFCLK_D";\n'
                f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(hmc7044_pll2_out_freq // 12)}\n"
                "\t\t\t\tadi,driver-mode = <1>;\n"
                "\t\t\t\tadi,coarse-digital-delay = <15>;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c3: channel@3 {\n"
                "\t\t\t\treg = <3>;\n"
                '\t\t\t\tadi,extended-name = "DEV_SYSREF_D";\n'
                f"\t\t\t\tadi,divider = <3840>; // {self._fmt_hz(hmc7044_pll2_out_freq // 3840)}\n"
                "\t\t\t\tadi,driver-mode = <2>;\n"
                "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
                "\t\t\t\tadi,high-performance-mode-disable;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c4: channel@4 {\n"
                "\t\t\t\treg = <4>;\n"
                '\t\t\t\tadi,extended-name = "JESD_REFCLK_TX_OBS_CD";\n'
                f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(hmc7044_pll2_out_freq // 12)}\n"
                "\t\t\t\tadi,driver-mode = <1>;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c5: channel@5 {\n"
                "\t\t\t\treg = <5>;\n"
                '\t\t\t\tadi,extended-name = "JESD_REFCLK_RX_CD";\n'
                f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(hmc7044_pll2_out_freq // 12)}\n"
                "\t\t\t\tadi,driver-mode = <1>;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c6: channel@6 {\n"
                "\t\t\t\treg = <6>;\n"
                '\t\t\t\tadi,extended-name = "FPGA_SYSREF_TX_OBS_CD";\n'
                f"\t\t\t\tadi,divider = <3840>; // {self._fmt_hz(hmc7044_pll2_out_freq // 3840)}\n"
                "\t\t\t\tadi,driver-mode = <2>;\n"
                "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
                "\t\t\t\tadi,high-performance-mode-disable;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c7: channel@7 {\n"
                "\t\t\t\treg = <7>;\n"
                '\t\t\t\tadi,extended-name = "FPGA_SYSREF_RX_CD";\n'
                f"\t\t\t\tadi,divider = <3840>; // {self._fmt_hz(hmc7044_pll2_out_freq // 3840)}\n"
                "\t\t\t\tadi,driver-mode = <2>;\n"
                "\t\t\t\tadi,startup-mode-dynamic-enable;\n"
                "\t\t\t\tadi,high-performance-mode-disable;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c8: channel@8 {\n"
                "\t\t\t\treg = <8>;\n"
                '\t\t\t\tadi,extended-name = "CORE_CLK_TX_OBS_CD";\n'
                f"\t\t\t\tadi,divider = <24>; // {self._fmt_hz(hmc7044_pll2_out_freq // 24)}\n"
                "\t\t\t\tadi,driver-mode = <2>;\n"
                "\t\t\t};\n"
                "\t\t\thmc7044_fmc_c9: channel@9 {\n"
                "\t\t\t\treg = <9>;\n"
                '\t\t\t\tadi,extended-name = "CORE_CLK_RX_CD";\n'
                f"\t\t\t\tadi,divider = <12>; // {self._fmt_hz(hmc7044_pll2_out_freq // 12)}\n"
                "\t\t\t\tadi,driver-mode = <2>;\n"
                "\t\t\t};\n"
            )
            clock_output_names = (
                '"hmc7044_fmc_out0_DEV_REFCLK_C", "hmc7044_fmc_out1_DEV_SYSREF_C", '
                '"hmc7044_fmc_out2_DEV_REFCLK_D", "hmc7044_fmc_out3_DEV_SYSREF_D", '
                '"hmc7044_fmc_out4_JESD_REFCLK_TX_OBS_CD", '
                '"hmc7044_fmc_out5_JESD_REFCLK_RX_CD", '
                '"hmc7044_fmc_out6_FPGA_SYSREF_TX_OBS_CD", '
                '"hmc7044_fmc_out7_FPGA_SYSREF_RX_CD", '
                '"hmc7044_fmc_out8_CORE_CLK_TX_OBS_CD", '
                '"hmc7044_fmc_out9_CORE_CLK_RX_CD", "hmc7044_fmc_out10", '
                '"hmc7044_fmc_out11", "hmc7044_fmc_out12", "hmc7044_fmc_out13";'
            )
            tx_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"
            rx_clkgen_ref = f"<&{clock_chip_label} {hmc7044_rx_channel}>"
            rx_os_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"
            rx_xcvr_clkgen_ref = f"<&{clock_chip_label} {hmc7044_xcvr_channel}>"
            rx_xcvr_div40_clk_ref = f"<&{clock_chip_label} {hmc7044_rx_channel}>"
            tx_xcvr_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_xcvr_channel}>"
            tx_xcvr_div40_clk_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"
            rx_os_xcvr_clkgen_ref = f"<&{clock_chip_label} {hmc7044_tx_xcvr_channel}>"
            rx_os_xcvr_div40_clk_ref = f"<&{clock_chip_label} {hmc7044_tx_channel}>"
            trx_clocks = [
                f"<&{clock_chip_label} {hmc7044_trx0_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_xcvr_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx0_sysref_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx0_sysref_fmc_channel}>",
            ]
            trx1_clocks = [
                f"<&{clock_chip_label} {hmc7044_trx1_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_xcvr_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx1_sysref_dev_channel}>",
                f"<&{clock_chip_label} {hmc7044_trx1_sysref_fmc_channel}>",
            ]
            custom_clock_chip_blocks = board_cfg.get("hmc7044_channel_blocks")
            clock_chip_node_prefix = f"\t\t{clock_chip_label}: hmc7044@{clk_cs} {{\n"
            clock_chip_node_props = (
                '	\t\tcompatible = "adi,hmc7044";\n'
                f"\t\t\treg = <{clk_cs}>;\n"
                "\t\t\t#address-cells = <1>;\n"
                "\t\t\t#size-cells = <0>;\n"
                "\t\t\t#clock-cells = <1>;\n"
                "\t\t\tspi-max-frequency = <10000000>;\n"
                f"\t\t\tadi,pll1-clkin-frequencies = <{_pll1_freqs_str}>;\n"
                "\t\t\tadi,pll1-ref-prio-ctrl = <0x1E>;\n"
                "\t\t\tadi,clkin0-buffer-mode = <0x07>;\n"
                "\t\t\tadi,clkin1-buffer-mode = <0x09>;\n"
                "\t\t\tadi,clkin2-buffer-mode = <0x05>;\n"
                "\t\t\tadi,clkin3-buffer-mode = <0x11>;\n"
                "\t\t\tadi,oscin-buffer-mode = <0x15>;\n"
                "\t\t\tadi,pll1-loop-bandwidth-hz = <200>;\n"
                f"\t\t\tadi,vcxo-frequency = <{hmc7044_vcxo_freq}>;\n"
                f"\t\t\tadi,pll2-output-frequency = <{hmc7044_pll2_out_freq}>;\n"
                "\t\t\tadi,sync-pin-mode = <1>;\n"
                "\t\t\tadi,pulse-generator-mode = <7>;\n"
                "\t\t\tadi,sysref-timer-divider = <3840>;\n"
                "\t\t\tadi,high-performance-mode-clock-dist-enable;\n"
                f"\t\t\tadi,gpi-controls = <{_gpi_str}>;\n"
                f"\t\t\tadi,gpo-controls = <{_gpo_str}>;\n"
            )
            ad9528_vcxo_freq = None
        else:
            clock_chip_label = "clk0_ad9528"
            tx_clkgen_ref = "<&clk0_ad9528 13>"
            rx_clkgen_ref = "<&clk0_ad9528 13>"
            rx_os_clkgen_ref = "<&clk0_ad9528 13>"
            rx_xcvr_clkgen_ref = "<&clk0_ad9528 1>"
            rx_xcvr_div40_clk_ref = "<&clk0_ad9528 1>"
            tx_xcvr_clkgen_ref = "<&clk0_ad9528 1>"
            tx_xcvr_div40_clk_ref = "<&clk0_ad9528 1>"
            rx_os_xcvr_clkgen_ref = "<&clk0_ad9528 1>"
            rx_os_xcvr_div40_clk_ref = "<&clk0_ad9528 1>"
            trx_clocks = [
                "<&clk0_ad9528 13>",
                "<&clk0_ad9528 1>",
                "<&clk0_ad9528 12>",
                "<&clk0_ad9528 3>",
            ]
            ad9528_vcxo_freq = int(board_cfg.get("ad9528_vcxo_freq", 122880000))
            # PLL2 output: vcxo * pll2-n2-div(10) / pll2-r1-div(1), channel-divider=5
            _ad9528_ch_freq = ad9528_vcxo_freq * 10 // 5
            default_clock_chip_channels_block = (
                "\t\t\tad9528_0_c13: channel@13 {\n"
                "\t\t\t\treg = <13>;\n"
                '\t\t\t\tadi,extended-name = "DEV_CLK";\n'
                "\t\t\t\tadi,driver-mode = <0>;\n"
                "\t\t\t\tadi,divider-phase = <0>;\n"
                f"\t\t\t\tadi,channel-divider = <5>; // {self._fmt_hz(_ad9528_ch_freq)}\n"
                "\t\t\t\tadi,signal-source = <0>;\n"
                "\t\t\t};\n"
                "\t\t\tad9528_0_c1: channel@1 {\n"
                "\t\t\t\treg = <1>;\n"
                '\t\t\t\tadi,extended-name = "FMC_CLK";\n'
                "\t\t\t\tadi,driver-mode = <0>;\n"
                "\t\t\t\tadi,divider-phase = <0>;\n"
                f"\t\t\t\tadi,channel-divider = <5>; // {self._fmt_hz(_ad9528_ch_freq)}\n"
                "\t\t\t\tadi,signal-source = <0>;\n"
                "\t\t\t};\n"
                "\t\t\tad9528_0_c12: channel@12 {\n"
                "\t\t\t\treg = <12>;\n"
                '\t\t\t\tadi,extended-name = "DEV_SYSREF";\n'
                "\t\t\t\tadi,driver-mode = <0>;\n"
                "\t\t\t\tadi,divider-phase = <0>;\n"
                "\t\t\t\tadi,channel-divider = <5>;\n"
                "\t\t\t\tadi,signal-source = <2>;\n"
                "\t\t\t};\n"
                "\t\t\tad9528_0_c3: channel@3 {\n"
                "\t\t\t\treg = <3>;\n"
                '\t\t\t\tadi,extended-name = "FMC_SYSREF";\n'
                "\t\t\t\tadi,driver-mode = <0>;\n"
                "\t\t\t\tadi,divider-phase = <0>;\n"
                "\t\t\t\tadi,channel-divider = <5>;\n"
                "\t\t\t\tadi,signal-source = <2>;\n"
                "\t\t\t};\n"
            )
            clock_output_names = (
                '"ad9528-1_out0", "ad9528-1_out1", "ad9528-1_out2", '
                '"ad9528-1_out3", "ad9528-1_out4", "ad9528-1_out5", '
                '"ad9528-1_out6", "ad9528-1_out7", "ad9528-1_out8", '
                '"ad9528-1_out9", "ad9528-1_out10", "ad9528-1_out11", '
                '"ad9528-1_out12", "ad9528-1_out13";'
            )
            custom_clock_chip_blocks = board_cfg.get("ad9528_channel_blocks")
            clock_chip_node_prefix = f"\t\t{clock_chip_label}: ad9528-1@{clk_cs} {{\n"
            clock_chip_node_props = (
                '	\t\tcompatible = "adi,ad9528";\n'
                f"\t\t\treg = <{clk_cs}>;\n"
                "\t\t\t#address-cells = <1>;\n"
                "\t\t\t#size-cells = <0>;\n"
                "\t\t\tspi-max-frequency = <10000000>;\n"
                "\t\t\tadi,refa-enable;\n"
                "\t\t\tadi,refa-diff-rcv-enable;\n"
                "\t\t\tadi,refa-r-div = <1>;\n"
                "\t\t\tadi,osc-in-cmos-neg-inp-enable;\n"
                "\t\t\tadi,pll1-feedback-div = <4>;\n"
                "\t\t\tadi,pll1-charge-pump-current-nA = <5000>;\n"
                "\t\t\tadi,pll2-vco-div-m1 = <3>;\n"
                "\t\t\tadi,pll2-n2-div = <10>;\n"
                "\t\t\tadi,pll2-r1-div = <1>;\n"
                "\t\t\tadi,pll2-charge-pump-current-nA = <805000>;\n"
                "\t\t\tadi,sysref-src = <2>;\n"
                "\t\t\tadi,sysref-pattern-mode = <1>;\n"
                "\t\t\tadi,sysref-k-div = <512>;\n"
                "\t\t\tadi,sysref-request-enable;\n"
                "\t\t\tadi,sysref-nshot-mode = <3>;\n"
                "\t\t\tadi,sysref-request-trigger-mode = <0>;\n"
                "\t\t\tadi,status-mon-pin0-function-select = <1>;\n"
                "\t\t\tadi,status-mon-pin1-function-select = <7>;\n"
                f"\t\t\tadi,vcxo-freq = <{ad9528_vcxo_freq}>;\n"
            )

        rx_dma_label = next(
            (
                lbl
                for lbl in labels
                if "_rx_dma" in lbl and "_obs_" not in lbl and "_os_" not in lbl
            ),
            "axi_adrv9009_rx_dma",
        )
        tx_dma_label = next(
            (lbl for lbl in labels if "_tx_dma" in lbl),
            "axi_adrv9009_tx_dma",
        )
        rx_os_dma_label = next(
            (lbl for lbl in labels if "_obs_dma" in lbl or "_rx_os_dma" in lbl),
            "axi_adrv9009_rx_os_dma",
        )

        rx_device_clk_ref = f"<&{rx_clkgen_label}>" if has_rx_clkgen else rx_clkgen_ref
        tx_device_clk_ref = f"<&{tx_clkgen_label}>" if has_tx_clkgen else tx_clkgen_ref
        rx_os_device_clk_ref = (
            f"<&{rx_os_clkgen_label}>" if has_rx_os_clkgen else rx_os_clkgen_ref
        )
        rx_xcvr_conv_clk_ref = (
            f"<&{rx_clkgen_label}>" if has_rx_clkgen else rx_xcvr_clkgen_ref
        )
        rx_xcvr_div40_ref = (
            f"<&{rx_clkgen_label}>" if has_rx_clkgen else rx_xcvr_div40_clk_ref
        )
        tx_xcvr_conv_clk_ref = (
            f"<&{tx_clkgen_label}>" if has_tx_clkgen else tx_xcvr_clkgen_ref
        )
        tx_xcvr_div40_ref = (
            f"<&{tx_clkgen_label}>" if has_tx_clkgen else tx_xcvr_div40_clk_ref
        )
        rx_os_xcvr_conv_clk_ref = (
            f"<&{rx_os_clkgen_label}>" if has_rx_os_clkgen else rx_os_xcvr_clkgen_ref
        )
        rx_os_xcvr_div40_ref = (
            f"<&{rx_os_clkgen_label}>" if has_rx_os_clkgen else rx_os_xcvr_div40_clk_ref
        )

        rx_link_id = int(board_cfg.get("rx_link_id", 1))
        rx_os_link_id = int(board_cfg.get("rx_os_link_id", 2))
        tx_link_id = int(board_cfg.get("tx_link_id", 0))
        tx_octets_per_frame = int(board_cfg.get("tx_octets_per_frame", 2))
        rx_os_octets_per_frame = int(board_cfg.get("rx_os_octets_per_frame", 2))
        trx_link_ids = [str(rx_link_id), str(tx_link_id)]
        trx_jesd_inputs = [
            f"<&{rx_xcvr_label} 0 {rx_link_id}>",
            f"<&{tx_xcvr_label} 0 {tx_link_id}>",
        ]
        if rx_os_jesd_label:
            trx_link_ids.insert(1, str(rx_os_link_id))
            trx_jesd_inputs.insert(1, f"<&{rx_os_xcvr_label} 0 {rx_os_link_id}>")

        trx_clock_names = [
            '"dev_clk"',
            '"fmc_clk"',
            '"sysref_dev_clk"',
            '"sysref_fmc_clk"',
        ]

        trx_clocks_value = ", ".join(trx_clocks)
        trx1_clocks_value = (
            ", ".join(trx1_clocks) if is_fmcomms8_layout else trx_clocks_value
        )
        trx_clock_names_value = ", ".join(trx_clock_names)
        trx_link_ids_value = " ".join(trx_link_ids)
        trx_inputs_value = ", ".join(trx_jesd_inputs)

        if custom_clock_chip_blocks:
            clock_chip_channels_block = "".join(
                self._format_nested_block(str(block))
                for block in custom_clock_chip_blocks
            )
        else:
            clock_chip_channels_block = default_clock_chip_channels_block

        default_trx_profile_props = [
            "adi,rx-profile-rx-fir-num-fir-coefs = <48>;",
            "adi,rx-profile-rx-fir-coefs = /bits/ 16 <(-2) (23) (46) (-17) (-104) (10) (208) (23) (-370) (-97) (607) (240) (-942) (-489) (1407) (910) (-2065) (-1637) (3058) (2995) (-4912) (-6526) (9941) (30489) (30489) (9941) (-6526) (-4912) (2995) (3058) (-1637) (-2065) (910) (1407) (-489) (-942) (240) (607) (-97) (-370) (23) (208) (10) (-104) (-17) (46) (23) (-2)>;",
            "adi,rx-profile-rx-adc-profile = /bits/ 16 <182 142 173 90 1280 982 1335 96 1369 48 1012 18 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;",
            "adi,orx-profile-rx-fir-num-fir-coefs = <24>;",
            "adi,orx-profile-rx-fir-coefs = /bits/ 16 <(-10) (7) (-10) (-12) (6) (-12) (16) (-16) (1) (63) (-431) (17235) (-431) (63) (1) (-16) (16) (-12) (6) (-12) (-10) (7) (-10) (0)>;",
            "adi,orx-profile-orx-low-pass-adc-profile = /bits/ 16 <185 141 172 90 1280 942 1332 90 1368 46 1016 19 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;",
            "adi,orx-profile-orx-band-pass-adc-profile = /bits/ 16 <0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0>;",
            "adi,orx-profile-orx-merge-filter = /bits/ 16 <0 0 0 0 0 0 0 0 0 0 0 0>;",
            "adi,tx-profile-tx-fir-num-fir-coefs = <40>;",
            "adi,tx-profile-tx-fir-coefs = /bits/ 16 <(-14) (5) (-9) (6) (-4) (19) (-29) (27) (-30) (46) (-63) (77) (-103) (150) (-218) (337) (-599) (1266) (-2718) (19537) (-2718) (1266) (-599) (337) (-218) (150) (-103) (77) (-63) (46) (-30) (27) (-29) (19) (-4) (6) (-9) (5) (-14) (0)>;",
            "adi,tx-profile-loop-back-adc-profile = /bits/ 16 <206 132 168 90 1280 641 1307 53 1359 28 1039 30 48 48 37 210 0 0 0 0 53 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;",
        ]
        trx_profile_props = board_cfg.get(
            "trx_profile_props", default_trx_profile_props
        )
        trx_profile_props_block = "".join(
            f"\t\t\t{prop}\n" for prop in trx_profile_props
        )

        if is_fmcomms8_layout:
            clock_chip_node = (
                f"{clock_chip_node_prefix}"
                f"{clock_chip_node_props}"
                f"\t\t\tclock-output-names = {clock_output_names}\n"
                f"{clock_chip_channels_block}"
                "\t\t};\n"
            )
        else:
            clock_chip_node = (
                f"{clock_chip_node_prefix}"
                f"{clock_chip_node_props}"
                f"\t\t\tclock-output-names = {clock_output_names}\\n"
                f"{clock_chip_channels_block}"
                "\t\t};\n"
            )

        nodes = [
            "\t&misc_clk_0 {\n"
            '\t\tcompatible = "fixed-clock";\n'
            "\t\t#clock-cells = <0>;\n"
            f"\t\tclock-frequency = <{misc_clk_hz}>;\n"
            "\t};",
            f"\t&{rx_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, {rx_device_clk_ref}, <&{rx_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\tadi,octets-per-frame = <{rx_f}>;\n"
            "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\tadi,frames-per-multiframe = <{rx_k}>;\n"
            f"\t\tjesd204-inputs = <&{rx_xcvr_label} 0 {rx_link_id}>;\n"
            "\t};",
            f"\t&{tx_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, {tx_device_clk_ref}, <&{tx_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
            f"\t\tadi,octets-per-frame = <{tx_octets_per_frame}>;\n"
            "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
            f"\t\tadi,frames-per-multiframe = <{tx_k}>;\n"
            "\t\tadi,converter-resolution = <14>;\n"
            "\t\tadi,bits-per-sample = <16>;\n"
            f"\t\tadi,converters-per-device = <{tx_m}>;\n"
            "\t\tadi,control-bits-per-sample = <2>;\n"
            f"\t\tjesd204-inputs = <&{tx_xcvr_label} 0 {tx_link_id}>;\n"
            "\t};",
            f"\t&{rx_dma_label} {{\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{tx_dma_label} {{\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{rx_os_dma_label} {{\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{rx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {rx_xcvr_conv_clk_ref}, {rx_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_gt_clk", "rx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
            f"\t&{rx_os_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {rx_os_xcvr_conv_clk_ref}, {rx_os_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_os_gt_clk", "rx_os_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
            f"\t&{tx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {tx_xcvr_conv_clk_ref}, {tx_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "tx_gt_clk", "tx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
            f"\t&{rx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-rx-1.0";\n'
            "\t\tadi,axi-decimation-core-available;\n"
            f"\t\tdmas = <&{rx_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t};",
            f"\t&{rx_os_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-obs-1.0";\n'
            f"\t\tdmas = <&{rx_os_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};",
            f"\t&{tx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-tx-1.0";\n'
            "\t\tadi,axi-interpolation-core-available;\n"
            f"\t\tdmas = <&{tx_dma_label} 0>;\n"
            '\t\tdma-names = "tx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};",
            f"\t&{spi_bus} {{\n"
            '\t\tstatus = "okay";\n'
            f"{clock_chip_node}"
            f"\t\t{phy_label}: {phy_node_name}@{trx_cs} {{\n"
            f"\t\t\tcompatible = {phy_compatible};\n"
            f"\t\t\treg = <{trx_cs}>;\n"
            f"\t\t\tspi-max-frequency = <{trx_spi_max_frequency}>;\n"
            f"\t\t\tclocks = {trx_clocks_value};\n"
            f"\t\t\tclock-names = {trx_clock_names_value};\n"
            "\t\t\t#clock-cells = <1>;\n"
            '\t\t\tclock-output-names = "rx_sampl_clk", "rx_os_sampl_clk", "tx_sampl_clk";\n'
            f"\t\t\treset-gpios = <&{gpio_label} {trx_reset_gpio} 0>;\n"
            f"\t\t\tsysref-req-gpios = <&{gpio_label} {trx_sysref_req_gpio} 0>;\n"
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <0>;\n"
            f"\t\t\tjesd204-link-ids = <{trx_link_ids_value}>;\n"
            f"\t\t\tjesd204-inputs = {trx_inputs_value};\n"
            f"{trx_profile_props_block}"
            "\t\t};\n"
            + (
                f"\t\ttrx1_{phy_family}: {phy_family}-phy@{trx2_cs} {{\n"
                f'\t\t\tcompatible = "{phy_family}";\n'
                f"\t\t\treg = <{trx2_cs}>;\n"
                f"\t\t\tspi-max-frequency = <{trx_spi_max_frequency}>;\n"
                f"\t\t\tclocks = {trx1_clocks_value};\n"
                f"\t\t\tclock-names = {trx_clock_names_value};\n"
                "\t\t\t#clock-cells = <1>;\n"
                '\t\t\tclock-output-names = "rx_sampl_clk", "rx_os_sampl_clk", "tx_sampl_clk";\n'
                f"\t\t\treset-gpios = <&{gpio_label} {trx2_reset_gpio} 0>;\n"
                "\t\t\tjesd204-device;\n"
                "\t\t\t#jesd204-cells = <2>;\n"
                "\t\t\tjesd204-top-device = <0>;\n"
                f"\t\t\tjesd204-link-ids = <{trx_link_ids_value}>;\n"
                f"\t\t\tjesd204-inputs = {trx_inputs_value};\n"
                f"{trx_profile_props_block}"
                "\t\t};\n"
                if is_fmcomms8_layout
                else ""
            )
            + "\t};",
            f"\t&{rx_core_label} {{\n\t\tspibus-connected = <&{phy_label}>;\n\t}};",
            f"\t&{rx_os_core_label} {{\n"
            f"\t\tclocks = <&{phy_label} 1>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};",
            f"\t&{tx_core_label} {{\n"
            f"\t\tspibus-connected = <&{phy_label}>;\n"
            f"\t\tclocks = <&{phy_label} 2>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};",
        ]
        if has_rx_clkgen:
            nodes.insert(
                1,
                f"\t&{rx_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f'\t\tclock-output-names = "{rx_clkgen_label}";\n'
                '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                "\t};",
            )
        if has_tx_clkgen:
            nodes.insert(
                2 if has_rx_clkgen else 1,
                f"\t&{tx_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f'\t\tclock-output-names = "{tx_clkgen_label}";\n'
                '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                "\t};",
            )
        if rx_os_jesd_label:
            if has_rx_os_clkgen:
                nodes.insert(
                    3 if has_rx_clkgen and has_tx_clkgen else 2,
                    f"\t&{rx_os_clkgen_label} {{\n"
                    '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                    "\t\t#clock-cells = <0>;\n"
                    f'\t\tclock-output-names = "{rx_os_clkgen_label}";\n'
                    '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                    "\t};",
                )
            nodes.insert(
                4 if has_rx_clkgen and has_tx_clkgen and has_rx_os_clkgen else 3,
                f"\t&{rx_os_jesd_label} {{\n"
                '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
                f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>, {rx_os_device_clk_ref}, <&{rx_os_xcvr_label} 0>;\n"
                '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
                "\t\t#clock-cells = <0>;\n"
                "\t\tjesd204-device;\n"
                "\t\t#jesd204-cells = <2>;\n"
                "\t\t/* JESD204 framing: F = octets per frame per lane */\n"
                f"\t\tadi,octets-per-frame = <{rx_os_octets_per_frame}>;\n"
                "\t\t/* JESD204 framing: K = frames per multiframe (subclass 1: 17–256, must be multiple of 4) */\n"
                f"\t\tadi,frames-per-multiframe = <{rx_k}>;\n"
                f"\t\tjesd204-inputs = <&{rx_os_xcvr_label} 0 {rx_os_link_id}>;\n"
                "\t};",
            )
        return nodes
