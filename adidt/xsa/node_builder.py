# adidt/xsa/node_builder.py
"""Build ADI device-driver DTS overlay nodes from an XSA topology and config."""

from copy import deepcopy
import os
import warnings
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .pipeline_config import PipelineConfig
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
    _AD9084_EBZ_VCU118_CLOCK_DEFAULTS: dict[str, Any] = {
        "rx_device_clk_label": "hmc7044",
        "rx_device_clk_index": 8,
        "tx_device_clk_label": "hmc7044",
        "tx_device_clk_index": 9,
        "rx_b_device_clk_index": 11,
        "tx_b_device_clk_index": 12,
    }
    _AD9084_EBZ_VCU118_BOARD_DEFAULTS: dict[str, Any] = {
        "converter_spi": "axi_spi_2",
        "converter_cs": 0,
        "clock_spi": "axi_spi",
        "hmc7044_cs": 1,
        "pll1_clkin_frequencies": [
            125_000_000,
            125_000_000,
            125_000_000,
            125_000_000,
        ],
        "vcxo_hz": 125_000_000,
        "pll2_output_hz": 2_500_000_000,
        "fpga_refclk_channel": 10,
        "dev_clk_source": "adf4382",
        "dev_clk_ref": "adf4382 0",
        "dev_clk_scales": "1 10",
        "adf4382_cs": 0,
        "rx_sys_clk_select": 3,
        "tx_sys_clk_select": 3,
        "rx_out_clk_select": 4,
        "tx_out_clk_select": 4,
        "rx_a_link_id": 4,
        "rx_b_link_id": 6,
        "tx_a_link_id": 0,
        "tx_b_link_id": 2,
        "firmware_name": "204C_M4_L8_NP16_1p25_4x4.bin",
        "reset_gpio": 62,
        "subclass": 0,
        "side_b_separate_tpl": True,
        "jrx0_physical_lane_mapping": "10 8 9 11 5 1 3 7 4 6 2 0",
        "jtx0_logical_lane_mapping": "11 2 3 5 10 1 9 0 6 7 8 4",
        "jrx1_physical_lane_mapping": "4 6 2 0 1 7 10 3 5 8 9 11",
        "jtx1_logical_lane_mapping": "3 9 5 4 2 6 1 7 8 11 0 10",
        "pulse_generator_mode": 7,
        "oscin_buffer_mode": "0x05",
        "hsci_label": "axi_hsci_0",
        "hsci_auto_linkup": True,
        "hmc7044_channels": [
            {"id": 1, "name": "ADF4030_REFIN", "divider": 20, "driver_mode": 2},
            {
                "id": 3,
                "name": "ADF4030_BSYNC0",
                "divider": 512,
                "driver_mode": 1,
                "is_sysref": True,
            },
            {"id": 8, "name": "CORE_CLK_TX", "divider": 8, "driver_mode": 2},
            {"id": 9, "name": "CORE_CLK_RX", "divider": 8, "driver_mode": 2},
            {"id": 10, "name": "FPGA_REFCLK", "divider": 8, "driver_mode": 2},
            {"id": 11, "name": "CORE_CLK_RX_B", "divider": 8, "driver_mode": 2},
            {"id": 12, "name": "CORE_CLK_TX_B", "divider": 8, "driver_mode": 2},
        ],
    }
    _ADRV90XX_KEYWORDS = ("adrv9009", "adrv9025", "adrv9026")

    @classmethod
    def _is_adrv90xx_name(cls, value: str) -> bool:
        """Return True if *value* contains an ADRV9009/9025/9026 keyword."""
        lower = value.lower()
        return any(key in lower for key in cls._ADRV90XX_KEYWORDS)

    # Platforms using single-cell (32-bit) addressing in amba_pl
    _32BIT_PLATFORMS = {"vcu118", "zc706"}

    def build(
        self, topology: XsaTopology, cfg: PipelineConfig | dict[str, Any]
    ) -> dict[str, list[str]]:
        """Render ADI DTS nodes.

        Args:
            topology: Parsed XSA topology.
            cfg: Pipeline configuration as a :class:`PipelineConfig` or raw dict.
                Dicts are used as-is for backward compatibility.  ``PipelineConfig``
                instances are converted to dict via :meth:`PipelineConfig.to_dict`.

        Returns:
            Dict with keys "jesd204_rx", "jesd204_tx", "converters".
        """
        if isinstance(cfg, PipelineConfig):
            cfg = cfg.to_dict()
        platform = topology.inferred_platform()
        self._addr_cells = 1 if platform in self._32BIT_PLATFORMS else 2
        # Invalidate cached Jinja env so reg_addr/reg_size pick up new cells
        if "_env" in self.__dict__:
            del self.__dict__["_env"]
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
        is_ad9084_design = any(c.ip_type == "axi_ad9084" for c in topology.converters)
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
            if is_ad9084_design:
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
            if is_ad9084_design:
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
            if is_ad9084_design and conv.ip_type == "axi_ad9084":
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
        result["converters"].extend(
            self._build_ad9084_nodes(
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
        spi_children = (
            self._render("ad9523_1.tmpl", self._build_ad9523_1_ctx(fmc))
            + self._render("ad9680.tmpl", self._build_ad9680_ctx(fmc))
            + self._render("ad9144.tmpl", self._build_ad9144_ctx(fmc))
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
            self._render(
                "jesd204_overlay.tmpl",
                self._build_jesd204_overlay_ctx(fmc, "rx", ps_clk_label, ps_clk_index),
            ),
            self._render(
                "jesd204_overlay.tmpl",
                self._build_jesd204_overlay_ctx(fmc, "tx", ps_clk_label, ps_clk_index),
            ),
            self._render("adxcvr.tmpl", self._build_adxcvr_ctx(fmc, "rx")),
            self._render("adxcvr.tmpl", self._build_adxcvr_ctx(fmc, "tx")),
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

        # Build ad9680 context for fmcdaq3: 1 clock, use_spi_3wire=True
        adc_gpio_lines = []
        for prop, attr in [
            ("powerdown-gpios", "adc_powerdown_gpio"),
            ("fastdetect-a-gpios", "adc_fastdetect_a_gpio"),
            ("fastdetect-b-gpios", "adc_fastdetect_b_gpio"),
        ]:
            val = getattr(fmc, attr, None)
            if val is not None:
                adc_gpio_lines.append(
                    {"prop": prop, "controller": fmc.gpio_controller, "index": int(val)}
                )
        ad9680_ctx = {
            "label": "adc0_ad9680",
            "cs": fmc.adc_cs,
            "spi_max_hz": fmc.adc_spi_max,
            "use_spi_3wire": True,
            "clks_str": f"<&clk0_ad9528 {fmc.adc_device_clk_idx}>",
            "clk_names_str": '"adc_clk"',
            "sampling_frequency_hz": fmc.adc_sampling_frequency_hz,
            "m": fmc.rx_m,
            "l": fmc.rx_l,
            "f": fmc.rx_f,
            "k": fmc.rx_k,
            "np": fmc.rx_np,
            "jesd204_top_device": 0,
            "jesd204_link_ids": [fmc.adc_jesd_link_id],
            "jesd204_inputs": f"{fmc.adc_core_label} 0 {fmc.adc_jesd_link_id}",
            "gpio_lines": adc_gpio_lines,
        }

        # SPI bus: ad9528 + ad9152 + ad9680
        spi_children = (
            self._render("ad9528.tmpl", self._build_ad9528_ctx(fmc))
            + self._render("ad9152.tmpl", self._build_ad9152_ctx(fmc))
            + self._render("ad9680.tmpl", ad9680_ctx)
        )

        # DMA nodes
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

        # TPL core nodes
        rx_tpl_ctx = {
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
        tx_tpl_ctx = {
            "label": fmc.dac_core_label,
            "compatible": "adi,axi-ad9144-1.0",
            "direction": "tx",
            "dma_label": fmc.dac_dma_label,
            "spibus_label": "dac0_ad9152",
            "jesd_label": fmc.dac_jesd_label,
            "jesd_link_offset": 1,
            "link_id": fmc.dac_jesd_link_id,
            "pl_fifo_enable": True,
            "sampl_clk_ref": None,
            "sampl_clk_name": None,
        }

        # JESD overlay contexts
        rx_jesd_ctx = {
            "label": fmc.adc_jesd_label,
            "direction": "rx",
            "clocks_str": f"<&{ps_clk_label} {ps_clk_index}>, <&{fmc.adc_xcvr_label} 1>, <&{fmc.adc_xcvr_label} 0>",
            "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
            "clock_output_name": "jesd_adc_lane_clk",
            "f": fmc.rx_f,
            "k": fmc.rx_k,
            "jesd204_inputs": f"{fmc.adc_xcvr_label} 0 {fmc.adc_jesd_link_id}",
            "converter_resolution": None,
            "converters_per_device": None,
            "bits_per_sample": None,
            "control_bits_per_sample": None,
        }
        tx_jesd_ctx = {
            "label": fmc.dac_jesd_label,
            "direction": "tx",
            "clocks_str": f"<&{ps_clk_label} {ps_clk_index}>, <&{fmc.dac_xcvr_label} 1>, <&{fmc.dac_xcvr_label} 0>",
            "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
            "clock_output_name": "jesd_dac_lane_clk",
            "f": fmc.tx_f,
            "k": fmc.tx_k,
            "jesd204_inputs": f"{fmc.dac_xcvr_label} 1 {fmc.dac_jesd_link_id}",
            "converter_resolution": None,
            "converters_per_device": fmc.tx_m,
            "bits_per_sample": fmc.tx_np,
            "control_bits_per_sample": 2,
        }

        # adxcvr contexts: 1-clock variant (use_div40=False), use_lpm_enable=True
        rx_xcvr_ctx = {
            "label": fmc.adc_xcvr_label,
            "sys_clk_select": fmc.adc_sys_clk_select,
            "out_clk_select": fmc.adc_out_clk_select,
            "clk_ref": f"clk0_ad9528 {fmc.adc_xcvr_ref_clk_idx}",
            "use_div40": False,
            "div40_clk_ref": None,
            "clock_output_names_str": '"adc_gt_clk", "rx_out_clk"',
            "use_lpm_enable": True,
            "jesd_l": None,
            "jesd_m": None,
            "jesd_s": None,
            "jesd204_inputs": "clk0_ad9528 0 0",
            "is_rx": True,
        }
        tx_xcvr_ctx = {
            "label": fmc.dac_xcvr_label,
            "sys_clk_select": fmc.dac_sys_clk_select,
            "out_clk_select": fmc.dac_out_clk_select,
            "clk_ref": f"clk0_ad9528 {fmc.dac_xcvr_ref_clk_idx}",
            "use_div40": False,
            "div40_clk_ref": None,
            "clock_output_names_str": '"dac_gt_clk", "tx_out_clk"',
            "use_lpm_enable": True,
            "jesd_l": None,
            "jesd_m": None,
            "jesd_s": None,
            "jesd204_inputs": None,
            "is_rx": False,
        }

        return [
            self._wrap_spi_bus(fmc.spi_bus, spi_children),
            dma_rx,
            dma_tx,
            self._render("tpl_core.tmpl", rx_tpl_ctx),
            self._render("tpl_core.tmpl", tx_tpl_ctx),
            self._render("jesd204_overlay.tmpl", rx_jesd_ctx),
            self._render("jesd204_overlay.tmpl", tx_jesd_ctx),
            self._render("adxcvr.tmpl", rx_xcvr_ctx),
            self._render("adxcvr.tmpl", tx_xcvr_ctx),
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
        _pll2 = ad.hmc7044_out_freq_hz
        channels = self._build_hmc7044_channel_ctx(
            _pll2,
            [
                {
                    "id": 2,
                    "name": "DAC_CLK",
                    "divider": 8,
                    "driver_mode": 1,
                    "is_sysref": False,
                },
                {
                    "id": 3,
                    "name": "DAC_SYSREF",
                    "divider": 512,
                    "driver_mode": 1,
                    "is_sysref": True,
                },
                {
                    "id": 12,
                    "name": "FPGA_CLK",
                    "divider": 8,
                    "driver_mode": 2,
                    "is_sysref": False,
                },
                {
                    "id": 13,
                    "name": "FPGA_SYSREF",
                    "divider": 512,
                    "driver_mode": 2,
                    "is_sysref": True,
                },
            ],
        )
        hmc7044_ctx = self._build_hmc7044_ctx(
            label="hmc7044",
            cs=ad.clock_cs,
            spi_max_hz=ad.clock_spi_max,
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
        spi_children = self._render("hmc7044.tmpl", hmc7044_ctx) + self._render(
            "ad9172.tmpl", self._build_ad9172_device_ctx(ad)
        )
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
        jesd_overlay_ctx = {
            "label": ad.dac_jesd_label,
            "direction": "tx",
            "clocks_str": f"<&{ps_clk_label} {ps_clk_index}>, <&{ad.dac_xcvr_label} 1>, <&{ad.dac_xcvr_label} 0>",
            "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
            "clock_output_name": "jesd_dac_lane_clk",
            "f": ad.tx_f,
            "k": ad.tx_k,
            "jesd204_inputs": f"{ad.dac_xcvr_label} 0 {ad.dac_jesd_link_id}",
            "converter_resolution": None,
            "converters_per_device": ad.tx_m,
            "bits_per_sample": ad.tx_np,
            "control_bits_per_sample": 0,
        }
        adxcvr_ctx = {
            "label": ad.dac_xcvr_label,
            "sys_clk_select": 3,
            "out_clk_select": 4,
            "clk_ref": "hmc7044 12",
            "use_div40": False,
            "div40_clk_ref": None,
            "clock_output_names_str": '"dac_gt_clk", "tx_out_clk"',
            "use_lpm_enable": True,
            "jesd_l": None,
            "jesd_m": None,
            "jesd_s": None,
            "jesd204_inputs": "hmc7044 0 0",
            "is_rx": False,
        }
        return [
            self._wrap_spi_bus(ad.spi_bus, spi_children),
            self._render("tpl_core.tmpl", tpl_ctx),
            self._render("jesd204_overlay.tmpl", jesd_overlay_ctx),
            self._render("adxcvr.tmpl", adxcvr_ctx),
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

    def _build_ad9528_ctx(self, fmc: "_FMCDAQ3Cfg") -> dict:
        """Build context dict for ad9528.tmpl from an _FMCDAQ3Cfg."""
        _m1 = 1_233_333_333  # adi,pll2-m1-frequency
        channels = [
            {
                "id": 2,
                "name": "DAC_CLK",
                "divider": 1,
                "freq_str": self._fmt_hz(_m1 // 1),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 4,
                "name": "DAC_CLK_FMC",
                "divider": 2,
                "freq_str": self._fmt_hz(_m1 // 2),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 5,
                "name": "DAC_SYSREF",
                "divider": 1,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 6,
                "name": "CLKD_DAC_SYSREF",
                "divider": 2,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 7,
                "name": "CLKD_ADC_SYSREF",
                "divider": 2,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 8,
                "name": "ADC_SYSREF",
                "divider": 1,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": True,
            },
            {
                "id": 9,
                "name": "ADC_CLK_FMC",
                "divider": 2,
                "freq_str": self._fmt_hz(_m1 // 2),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 13,
                "name": "ADC_CLK",
                "divider": 1,
                "freq_str": self._fmt_hz(_m1 // 1),
                "signal_source": 0,
                "is_sysref": False,
            },
        ]
        return {
            "label": "clk0_ad9528",
            "cs": fmc.clock_cs,
            "spi_max_hz": fmc.clock_spi_max,
            "vcxo_hz": fmc.clock_vcxo_hz,
            "gpio_lines": [],
            "channels": channels,
        }

    def _build_ad9528_1_ctx(self, board_cfg: dict) -> dict:
        """Build context dict for ad9528_1.tmpl from an ADRV9009 non-FMComms8 board config.

        The ad9528-1 variant is used by standard (non-FMComms8) ADRV9009 designs.
        It shares the same ``"adi,ad9528"`` compatible string but uses ADRV9009-specific
        PLL and sysref properties, and names its clock outputs ``ad9528-1_out{n}``.

        Context schema:
            label (str): DTS node label, always ``"clk0_ad9528"``.
            cs (int): SPI chip-select index.
            spi_max_hz (int): Maximum SPI bus frequency in Hz.
            vcxo_hz (int): VCXO frequency in Hz.
            gpio_lines (list[dict]): GPIO property dicts (empty for standard designs).
            channels (list[dict]): Per-channel dicts with keys:
                id (int), name (str), divider (int), freq_str (str),
                signal_source (int), is_sysref (bool).
        """
        clk_cs = int(board_cfg.get("clk_cs", 0))
        vcxo_hz = int(board_cfg.get("ad9528_vcxo_freq", 122880000))
        # PLL2 output: vcxo * pll2-n2-div(10) / pll2-r1-div(1), channel-divider=5
        ch_freq = vcxo_hz * 10 // 5
        channels = [
            {
                "id": 13,
                "name": "DEV_CLK",
                "divider": 5,
                "freq_str": self._fmt_hz(ch_freq),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 1,
                "name": "FMC_CLK",
                "divider": 5,
                "freq_str": self._fmt_hz(ch_freq),
                "signal_source": 0,
                "is_sysref": False,
            },
            {
                "id": 12,
                "name": "DEV_SYSREF",
                "divider": 5,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": False,
            },
            {
                "id": 3,
                "name": "FMC_SYSREF",
                "divider": 5,
                "freq_str": "",
                "signal_source": 2,
                "is_sysref": False,
            },
        ]
        return {
            "label": "clk0_ad9528",
            "cs": clk_cs,
            "spi_max_hz": 10000000,
            "vcxo_hz": vcxo_hz,
            "gpio_lines": [],
            "channels": channels,
        }

    def _build_adrv9009_device_ctx(
        self,
        phy_family: str,
        phy_compatible: str,
        trx_cs: int,
        trx_spi_max_frequency: int,
        gpio_label: str,
        trx_reset_gpio: int,
        trx_sysref_req_gpio: int,
        trx_clocks_value: str,
        trx_clock_names_value: str,
        trx_link_ids_value: str,
        trx_inputs_value: str,
        trx_profile_props_block: str,
        is_fmcomms8: bool,
        trx2_cs: "int | None" = None,
        trx2_reset_gpio: "int | None" = None,
        trx1_clocks_value: "str | None" = None,
    ) -> dict:
        """Build context dict for adrv9009.tmpl.

        Covers both standard single-chip and dual-chip FMComms8 ADRV9009/9025 designs.

        Context schema:
            phy_label (str): DTS label for the primary PHY, e.g. ``"trx0_adrv9009"``.
            phy_node_name (str): DTS node name, e.g. ``"adrv9009-phy"``.
            phy_compatible (str): DTS compatible string, e.g.
                ``'"adi,adrv9009", "adrv9009"'`` or ``'"adrv9009-x2"'``.
            trx_cs (int): SPI chip-select for primary PHY.
            spi_max_hz (int): Maximum SPI frequency in Hz.
            gpio_label (str): GPIO controller label, e.g. ``"gpio"`` or ``"gpio0"``.
            trx_reset_gpio (int): Reset GPIO line index for primary PHY.
            trx_sysref_req_gpio (int): SYSREF request GPIO line index.
            trx_clocks_value (str): Rendered ``clocks = ...`` value for primary PHY.
            trx_clock_names_value (str): Rendered ``clock-names = ...`` value.
            trx_link_ids_value (str): Space-separated link IDs for ``jesd204-link-ids``.
            trx_inputs_value (str): Rendered ``jesd204-inputs = ...`` value (shared by both PHYs).
            trx_profile_props_block (str): Pre-indented profile property lines block.
            is_fmcomms8 (bool): True for dual-chip FMComms8 layout.
            trx1_phy_compatible (str | None): Bare family name for second PHY compatible string
                (FMComms8 only), e.g. ``"adrv9009"``.
            trx2_cs (int | None): SPI chip-select for second PHY (FMComms8 only).
            trx2_reset_gpio (int | None): Reset GPIO for second PHY (FMComms8 only).
            trx1_clocks_value (str | None): ``clocks`` value for second PHY (FMComms8 only).
        """
        phy_label = f"trx0_{phy_family}"
        phy_node_name = f"{phy_family}-phy"
        trx1_phy_label = f"trx1_{phy_family}" if is_fmcomms8 else None
        return {
            "phy_label": phy_label,
            "phy_node_name": phy_node_name,
            "phy_compatible": phy_compatible,
            "trx_cs": trx_cs,
            "spi_max_hz": trx_spi_max_frequency,
            "gpio_label": gpio_label,
            "trx_reset_gpio": trx_reset_gpio,
            "trx_sysref_req_gpio": trx_sysref_req_gpio,
            "trx_clocks_value": trx_clocks_value,
            "trx_clock_names_value": trx_clock_names_value,
            "trx_link_ids_value": trx_link_ids_value,
            "trx_inputs_value": trx_inputs_value,
            "trx_profile_props_block": trx_profile_props_block,
            "is_fmcomms8": is_fmcomms8,
            "trx1_phy_label": trx1_phy_label,
            "trx1_phy_compatible": phy_family,
            "trx2_cs": trx2_cs,
            "trx2_reset_gpio": trx2_reset_gpio,
            "trx1_clocks_value": trx1_clocks_value,
        }

    _addr_cells: int = 2

    def _make_jinja_env(self) -> Environment:
        """Create and return a Jinja2 Environment pointed at the XSA template directory."""
        from .exceptions import XsaParseError

        loc = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "..", "templates", "xsa"
        )
        if not os.path.isdir(loc):
            raise XsaParseError(f"template directory not found: {loc}")
        env = Environment(loader=FileSystemLoader(loc))
        # Register reg-formatting globals used by clkgen/jesd templates.
        # The number of address/size cells depends on the target platform
        # (e.g. 1 for MicroBlaze, 2 for ZynqMP).
        cells = self._addr_cells
        env.globals["reg_addr"] = lambda addr: (
            f"0x{addr:08x}" if cells == 1 else f"0x0 0x{addr:08x}"
        )
        env.globals["reg_size"] = lambda size: (
            f"0x{size:x}" if cells == 1 else f"0x0 0x{size:x}"
        )
        return env

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
            "\t\t#address-cells = <1>;\n"
            "\t\t#size-cells = <0>;\n"
            f"{children}"
            "\t};"
        )

    @staticmethod
    def _fmt_gpi_gpo(controls: list) -> str:
        """Format a list of int/hex values as a space-separated hex string for DTS."""
        return " ".join(f"0x{int(v):02x}" for v in controls)

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
        clkin2_buffer_mode: "str | None" = None,
        clkin3_buffer_mode: "str | None" = None,
        oscin_buffer_mode=None,
        gpi_controls=None,
        gpo_controls=None,
        sync_pin_mode=None,
        high_perf_mode_dist_enable: bool = False,
        clkin0_ref: str | None = None,
    ) -> dict:
        """Build the context dict for hmc7044.tmpl."""
        clock_output_names_str = ", ".join(f'"{n}"' for n in clock_output_names)
        return {
            "label": label,
            "cs": cs,
            "spi_max_hz": spi_max_hz,
            "clkin0_ref": clkin0_ref,
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
            "clkin2_buffer_mode": clkin2_buffer_mode,
            "clkin3_buffer_mode": clkin3_buffer_mode,
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
            {
                "id": 1,
                "name": "DAC_CLK",
                "divider": 1,
                "freq_str": self._fmt_hz(_m1 // 1),
            },
            {
                "id": 4,
                "name": "ADC_CLK_FMC",
                "divider": 2,
                "freq_str": self._fmt_hz(_m1 // 2),
            },
            {
                "id": 5,
                "name": "ADC_SYSREF",
                "divider": 128,
                "freq_str": self._fmt_hz(_m1 // 128),
            },
            {
                "id": 6,
                "name": "CLKD_ADC_SYSREF",
                "divider": 128,
                "freq_str": self._fmt_hz(_m1 // 128),
            },
            {
                "id": 7,
                "name": "CLKD_DAC_SYSREF",
                "divider": 128,
                "freq_str": self._fmt_hz(_m1 // 128),
            },
            {
                "id": 8,
                "name": "DAC_SYSREF",
                "divider": 128,
                "freq_str": self._fmt_hz(_m1 // 128),
            },
            {
                "id": 9,
                "name": "FMC_DAC_REF_CLK",
                "divider": 2,
                "freq_str": self._fmt_hz(_m1 // 2),
            },
            {
                "id": 13,
                "name": "ADC_CLK",
                "divider": 1,
                "freq_str": self._fmt_hz(_m1 // 1),
            },
        ]
        gpio_lines = []
        for prop, attr, cfg_key in [
            ("sync-gpios", "clk_sync_gpio", "clk_sync_gpio"),
            ("status0-gpios", "clk_status0_gpio", "clk_status0_gpio"),
            ("status1-gpios", "clk_status1_gpio", "clk_status1_gpio"),
        ]:
            val = getattr(fmc, attr, None)
            if val is not None:
                gpio_idx = self._coerce_board_int(val, f"fmcdaq2_board.{cfg_key}")
                gpio_lines.append(
                    {"prop": prop, "controller": fmc.gpio_controller, "index": gpio_idx}
                )
        return {
            "label": "clk0_ad9523",
            "cs": fmc.clock_cs,
            "spi_max_hz": fmc.clock_spi_max,
            "vcxo_hz": fmc.clock_vcxo_hz,
            "gpio_lines": gpio_lines,
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
                gpio_lines.append(
                    {"prop": prop, "controller": fmc.gpio_controller, "index": int(val)}
                )
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
            "m": fmc.rx_m,
            "l": fmc.rx_l,
            "f": fmc.rx_f,
            "k": fmc.rx_k,
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
                gpio_lines.append(
                    {"prop": prop, "controller": fmc.gpio_controller, "index": int(val)}
                )
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

    def _build_ad9152_ctx(self, fmc: "_FMCDAQ3Cfg") -> dict:
        """Build context dict for ad9152.tmpl (fmcdaq3)."""
        gpio_lines = []
        for prop, attr in [
            ("txen-gpios", "dac_txen_gpio"),
            ("irq-gpios", "dac_irq_gpio"),
        ]:
            val = getattr(fmc, attr, None)
            if val is not None:
                gpio_lines.append(
                    {"prop": prop, "controller": fmc.gpio_controller, "index": int(val)}
                )
        return {
            "label": "dac0_ad9152",
            "cs": fmc.dac_cs,
            "spi_max_hz": fmc.dac_spi_max,
            "clk_ref": f"clk0_ad9528 {fmc.dac_device_clk_idx}",
            "jesd_link_mode": fmc.ad9152_jesd_link_mode,
            "jesd204_top_device": 1,
            "jesd204_link_ids": [fmc.dac_jesd_link_id],
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

    def _build_ad9081_mxfe_ctx(
        self,
        label: str,
        cs: int,
        gpio_label: str,
        reset_gpio: int,
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
        spi_max_hz: int = 5000000,
    ) -> dict:
        """Build context dict for ad9081_mxfe.tmpl (the AD9081 SPI device node)."""
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
    def _platform_ps_labels(topology: XsaTopology) -> tuple[str, int | None, str]:
        """Return ``(ps_clk_label, ps_clk_index, gpio_label)`` appropriate for the topology's platform."""
        platform = topology.inferred_platform()
        if platform == "zc706":
            return ("clkc", 15, "gpio0")
        if platform == "vcu118":
            # MicroBlaze/VCU118: AXI bus clock is a fixed-clock with #clock-cells = <0>
            return ("clk_bus_0", None, "axi_gpio")
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

        # HMC7044 channel configuration
        _pll2 = 3_000_000_000
        custom_hmc7044_blocks = ad9081_board_cfg.get("hmc7044_channel_blocks")
        if custom_hmc7044_blocks:
            raw_channels = "".join(
                self._format_nested_block(str(block)) for block in custom_hmc7044_blocks
            )
            hmc7044_channels = None
        else:
            raw_channels = None
            hmc7044_channels = self._build_hmc7044_channel_ctx(
                _pll2,
                [
                    {"id": 0, "name": "CORE_CLK_RX", "divider": 12, "driver_mode": 2},
                    {"id": 2, "name": "DEV_REFCLK", "divider": 12, "driver_mode": 2},
                    {
                        "id": 3,
                        "name": "DEV_SYSREF",
                        "divider": 1536,
                        "driver_mode": 2,
                        "is_sysref": True,
                    },
                    {"id": 6, "name": "CORE_CLK_TX", "divider": 12, "driver_mode": 2},
                    {"id": 8, "name": "FPGA_REFCLK1", "divider": 6, "driver_mode": 2},
                    {
                        "id": 10,
                        "name": "CORE_CLK_RX_ALT",
                        "divider": 12,
                        "driver_mode": 2,
                    },
                    {"id": 12, "name": "FPGA_REFCLK2", "divider": 6, "driver_mode": 2},
                    {
                        "id": 13,
                        "name": "FPGA_SYSREF",
                        "divider": 1536,
                        "driver_mode": 2,
                        "is_sysref": True,
                    },
                ],
            )

        # HMC7044 clock output names (14 outputs)
        hmc7044_clock_output_names = [f"hmc7044_out{i}" for i in range(14)]

        # Build HMC7044 context and render
        hmc7044_ctx = self._build_hmc7044_ctx(
            label="hmc7044",
            cs=clock_cs,
            spi_max_hz=1000000,
            pll1_clkin_frequencies=[122880000, 10000000, 0, 0],
            vcxo_hz=122880000,
            pll2_output_hz=_pll2,
            clock_output_names=hmc7044_clock_output_names,
            channels=hmc7044_channels,
            raw_channels=raw_channels,
            jesd204_sysref_provider=True,
            jesd204_max_sysref_hz=2000000,
            pll1_loop_bandwidth_hz=200,
            pll1_ref_prio_ctrl="0xE1",
            pll1_ref_autorevert=True,
            pll1_charge_pump_ua=720,
            pfd1_max_freq_hz=1000000,
            sysref_timer_divider=1024,
            pulse_generator_mode=0,
            clkin0_buffer_mode="0x07",
            clkin1_buffer_mode="0x07",
            oscin_buffer_mode="0x15",
            gpi_controls=[0x00, 0x00, 0x00, 0x00],
            gpo_controls=[0x37, 0x33, 0x00, 0x00],
        )

        # Build AD9081 MxFE device context and render
        ad9081_mxfe_ctx = self._build_ad9081_mxfe_ctx(
            label="trx0_ad9081",
            cs=adc_cs,
            gpio_label=gpio_label,
            reset_gpio=reset_gpio,
            sysref_req_gpio=sysref_req_gpio,
            rx2_enable_gpio=rx2_enable_gpio,
            rx1_enable_gpio=rx1_enable_gpio,
            tx2_enable_gpio=tx2_enable_gpio,
            tx1_enable_gpio=tx1_enable_gpio,
            dev_clk_ref="hmc7044 2",
            rx_core_label="rx_mxfe_tpl_core_adc_tpl_core",
            tx_core_label="tx_mxfe_tpl_core_dac_tpl_core",
            rx_link_id=rx_link_id,
            tx_link_id=tx_link_id,
            dac_frequency_hz=dac_frequency_hz,
            tx_cduc_interpolation=tx_cduc_interpolation,
            tx_fduc_interpolation=tx_fduc_interpolation,
            tx_converter_select=tx_converter_select,
            tx_lane_map=tx_lane_map,
            tx_link_mode=tx_link_mode,
            tx_m=tx_m,
            tx_f=tx_f,
            tx_k=tx_k,
            tx_l=tx_l,
            tx_s=tx_s,
            adc_frequency_hz=adc_frequency_hz,
            rx_cddc_decimation=rx_cddc_decimation,
            rx_fddc_decimation=rx_fddc_decimation,
            rx_converter_select=rx_converter_select,
            rx_lane_map=rx_lane_map,
            rx_link_mode=rx_link_mode,
            rx_m=rx_m,
            rx_f=rx_f,
            rx_k=rx_k,
            rx_l=rx_l,
            rx_s=rx_s,
        )

        # DMA nodes (no template — keep as raw strings)
        dma_rx = (
            "\t&axi_mxfe_rx_dma {\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};"
        )
        dma_tx = (
            "\t&axi_mxfe_tx_dma {\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};"
        )

        # adxcvr RX context (AD9081: 1-clock, use_lpm_enable=False)
        adxcvr_rx_ctx = {
            "label": "axi_mxfe_rx_xcvr",
            "sys_clk_select": rx_sys_clk_select,
            "out_clk_select": rx_out_clk_select,
            "clk_ref": "hmc7044 12",
            "use_div40": False,
            "div40_clk_ref": None,
            "clock_output_names_str": '"rx_gt_clk", "rx_out_clk"',
            "use_lpm_enable": False,
            "jesd_l": None,
            "jesd_m": None,
            "jesd_s": None,
            "jesd204_inputs": f"hmc7044 0 {rx_link_id}",
            "is_rx": True,
        }

        # adxcvr TX context (AD9081: 1-clock, use_lpm_enable=False)
        adxcvr_tx_ctx = {
            "label": "axi_mxfe_tx_xcvr",
            "sys_clk_select": tx_sys_clk_select,
            "out_clk_select": tx_out_clk_select,
            "clk_ref": "hmc7044 12",
            "use_div40": False,
            "div40_clk_ref": None,
            "clock_output_names_str": '"tx_gt_clk", "tx_out_clk"',
            "use_lpm_enable": False,
            "jesd_l": None,
            "jesd_m": None,
            "jesd_s": None,
            "jesd204_inputs": f"hmc7044 0 {tx_link_id}",
            "is_rx": False,
        }

        # TPL core RX context (pl_fifo_enable=False, no sampl_clk)
        tpl_rx_ctx = {
            "label": "rx_mxfe_tpl_core_adc_tpl_core",
            "compatible": "adi,axi-ad9081-rx-1.0",
            "direction": "rx",
            "dma_label": "axi_mxfe_rx_dma",
            "spibus_label": "trx0_ad9081",
            "jesd_label": "axi_mxfe_rx_jesd_rx_axi",
            "jesd_link_offset": 0,
            "link_id": rx_link_id,
            "pl_fifo_enable": False,
            "sampl_clk_ref": None,
            "sampl_clk_name": None,
        }

        # TPL core TX context (pl_fifo_enable=False, has sampl_clk)
        tpl_tx_ctx = {
            "label": "tx_mxfe_tpl_core_dac_tpl_core",
            "compatible": "adi,axi-ad9081-tx-1.0",
            "direction": "tx",
            "dma_label": "axi_mxfe_tx_dma",
            "spibus_label": "trx0_ad9081",
            "jesd_label": "axi_mxfe_tx_jesd_tx_axi",
            "jesd_link_offset": 0,
            "link_id": tx_link_id,
            "pl_fifo_enable": False,
            "sampl_clk_ref": "trx0_ad9081 1",
            "sampl_clk_name": "sampl_clk",
        }

        nodes = [
            dma_rx,
            dma_tx,
            self._render("adxcvr.tmpl", adxcvr_rx_ctx),
            self._render("adxcvr.tmpl", adxcvr_tx_ctx),
            self._render("tpl_core.tmpl", tpl_rx_ctx),
            self._render("tpl_core.tmpl", tpl_tx_ctx),
            self._wrap_spi_bus(clock_spi, self._render("hmc7044.tmpl", hmc7044_ctx)),
            self._wrap_spi_bus(
                adc_spi, self._render("ad9081_mxfe.tmpl", ad9081_mxfe_ctx)
            ),
        ]

        # JESD overlay nodes for mxfe instances
        for jesd in topology.jesd204_rx:
            lbl = jesd.name.replace("-", "_")
            if "mxfe" not in lbl:
                continue
            clocks_str = f"<&{ps_clk_label} {ps_clk_index}>, <&hmc7044 {rx_chan}>, <&axi_mxfe_rx_xcvr 0>"
            nodes.append(
                self._render(
                    "jesd204_overlay.tmpl",
                    {
                        "label": lbl,
                        "direction": "rx",
                        "clocks_str": clocks_str,
                        "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
                        "clock_output_name": None,
                        "f": rx_f,
                        "k": rx_k,
                        "jesd204_inputs": f"axi_mxfe_rx_xcvr 0 {rx_link_id}",
                        "converter_resolution": None,
                        "converters_per_device": None,
                        "bits_per_sample": None,
                        "control_bits_per_sample": None,
                    },
                )
            )
        for jesd in topology.jesd204_tx:
            lbl = jesd.name.replace("-", "_")
            if "mxfe" not in lbl:
                continue
            clocks_str = f"<&{ps_clk_label} {ps_clk_index}>, <&hmc7044 {tx_chan}>, <&axi_mxfe_tx_xcvr 0>"
            nodes.append(
                self._render(
                    "jesd204_overlay.tmpl",
                    {
                        "label": lbl,
                        "direction": "tx",
                        "clocks_str": clocks_str,
                        "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
                        "clock_output_name": None,
                        "f": tx_f,
                        "k": tx_k,
                        "jesd204_inputs": f"axi_mxfe_tx_xcvr 0 {tx_link_id}",
                        "converter_resolution": None,
                        "converters_per_device": None,
                        "bits_per_sample": None,
                        "control_bits_per_sample": None,
                    },
                )
            )

        return nodes

    def _build_ad9084_nodes(
        self,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int,
        gpio_label: str,
    ) -> list[str]:
        """Build DTS node strings for an AD9084 dual-link design.

        The AD9084 HDL design ("apollo") has two links per direction (a + b),
        each with its own JESD, XCVR, DMA, and TPL core.  This method emits
        overlay nodes for all FPGA IPs plus the board-level SPI devices
        (HMC7044 clock chip and AD9084 converter).

        Returns an empty list if the topology does not contain an AD9084 converter.
        """
        has_ad9084 = any(c.ip_type == "axi_ad9084" for c in topology.converters)
        if not has_ad9084:
            return []

        jesd_cfg = cfg.get("jesd", {})
        rx_cfg = jesd_cfg.get("rx", {})
        tx_cfg = jesd_cfg.get("tx", {})
        rx_f = int(rx_cfg.get("F", 6))
        rx_k = int(rx_cfg.get("K", 32))
        tx_f = int(tx_cfg.get("F", 6))
        tx_k = int(tx_cfg.get("K", 32))
        clock_cfg = deepcopy(cfg.get("clock", {}))
        board_cfg = deepcopy(cfg.get("ad9084_board", {}))
        if topology.inferred_platform() == "vcu118":
            for key, value in self._AD9084_EBZ_VCU118_CLOCK_DEFAULTS.items():
                clock_cfg.setdefault(key, deepcopy(value))
            for key, value in self._AD9084_EBZ_VCU118_BOARD_DEFAULTS.items():
                board_cfg.setdefault(key, deepcopy(value))

        # Per-link device_clk from clock config
        rx_dev_clk_label = str(clock_cfg.get("rx_device_clk_label", "axi_hsci_clkgen"))
        rx_dev_clk_index = clock_cfg.get("rx_device_clk_index", 0)
        tx_dev_clk_label = str(clock_cfg.get("tx_device_clk_label", rx_dev_clk_label))
        tx_dev_clk_index = clock_cfg.get("tx_device_clk_index", rx_dev_clk_index)
        rx_b_dev_clk_index = clock_cfg.get("rx_b_device_clk_index", rx_dev_clk_index)
        tx_b_dev_clk_index = clock_cfg.get("tx_b_device_clk_index", tx_dev_clk_index)

        # XCVR PLL selection (defaults for VCU118 GTY)
        rx_sys_clk_select = int(board_cfg.get("rx_sys_clk_select", 3))
        tx_sys_clk_select = int(board_cfg.get("tx_sys_clk_select", 3))
        rx_out_clk_select = int(board_cfg.get("rx_out_clk_select", 4))
        tx_out_clk_select = int(board_cfg.get("tx_out_clk_select", 4))

        # JESD204 link IDs for the four links
        rx_a_link_id = int(board_cfg.get("rx_a_link_id", 0))
        rx_b_link_id = int(board_cfg.get("rx_b_link_id", 1))
        tx_a_link_id = int(board_cfg.get("tx_a_link_id", 2))
        tx_b_link_id = int(board_cfg.get("tx_b_link_id", 3))

        # SPI configuration
        converter_spi = str(board_cfg.get("converter_spi", "axi_spi_2"))
        converter_cs = int(board_cfg.get("converter_cs", 0))
        clock_spi = str(board_cfg.get("clock_spi", "axi_spi"))
        hmc7044_cs = int(board_cfg.get("hmc7044_cs", 0))

        # HMC7044 configuration
        vcxo_hz = int(board_cfg.get("vcxo_hz", 125_000_000))
        pll2_output_hz = int(board_cfg.get("pll2_output_hz", 2_500_000_000))

        # HMC7044 channel index that provides the FPGA reference clock
        fpga_refclk_channel = int(board_cfg.get("fpga_refclk_channel", 10))

        # Firmware / profile
        firmware_name = board_cfg.get("firmware_name")
        reset_gpio = board_cfg.get("reset_gpio")

        # Derive instance names from topology JESD names.  The AD9084 "apollo"
        # design uses a consistent naming convention:
        #   JESD:     axi_apollo_{dir}[_b]_jesd_{dir}_axi
        #   XCVR:     axi_apollo_{dir}[_b]_xcvr
        #   DMA:      axi_apollo_{dir}[_b]_dma
        #   TPL ADC:  [rx|rx_b]_apollo_tpl_core_adc_tpl_core
        #   TPL DAC:  [tx|tx_b]_apollo_tpl_core_dac_tpl_core

        # Categorise JESD instances into (direction, link_variant) tuples
        rx_a_jesd = rx_b_jesd = tx_a_jesd = tx_b_jesd = None
        for j in topology.jesd204_rx:
            n = j.name.lower()
            if "_b_" in n or n.startswith("axi_apollo_rx_b"):
                rx_b_jesd = j
            else:
                rx_a_jesd = j
        for j in topology.jesd204_tx:
            n = j.name.lower()
            if "_b_" in n or n.startswith("axi_apollo_tx_b"):
                tx_b_jesd = j
            else:
                tx_a_jesd = j

        # Build link descriptors for each (direction, variant) pair
        _Link = type("_Link", (), {})
        links: list[_Link] = []
        for jesd, direction, variant, link_id, sys_sel, out_sel in [
            (rx_a_jesd, "rx", "", rx_a_link_id, rx_sys_clk_select, rx_out_clk_select),
            (rx_b_jesd, "rx", "_b", rx_b_link_id, rx_sys_clk_select, rx_out_clk_select),
            (tx_a_jesd, "tx", "", tx_a_link_id, tx_sys_clk_select, tx_out_clk_select),
            (tx_b_jesd, "tx", "_b", tx_b_link_id, tx_sys_clk_select, tx_out_clk_select),
        ]:
            if jesd is None:
                continue
            lk = _Link()
            lk.jesd = jesd
            lk.direction = direction
            lk.variant = variant
            lk.link_id = link_id
            lk.sys_clk_select = sys_sel
            lk.out_clk_select = out_sel
            # Infer sibling label names from JESD instance name
            #   axi_apollo_rx_b_jesd_rx_axi → prefix = axi_apollo_rx_b
            prefix = jesd.name.replace(f"_jesd_{direction}_axi", "")
            lk.jesd_label = jesd.name.replace("-", "_")
            lk.xcvr_label = f"{prefix}_xcvr"
            lk.dma_label = f"{prefix}_dma"
            # TPL core naming uses a different convention
            if direction == "rx":
                if variant:
                    lk.tpl_label = f"rx_b_apollo_tpl_core_adc_tpl_core"
                else:
                    lk.tpl_label = f"rx_apollo_tpl_core_adc_tpl_core"
                lk.tpl_compatible = "adi,axi-ad9081-rx-1.0"
            else:
                if variant:
                    lk.tpl_label = f"tx_b_apollo_tpl_core_dac_tpl_core"
                else:
                    lk.tpl_label = f"tx_apollo_tpl_core_dac_tpl_core"
                lk.tpl_compatible = "adi,axi-ad9081-tx-1.0"
            links.append(lk)

        nodes: list[str] = []

        # --- DMA overlay nodes ---
        for lk in links:
            nodes.append(
                f"\t&{lk.dma_label} {{\n"
                '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
                "\t\t#dma-cells = <1>;\n"
                "\t\t#clock-cells = <0>;\n"
                f"\t\tclocks = <&{ps_clk_label}"
                + (f" {ps_clk_index}" if ps_clk_index is not None else "")
                + ">;\n"
                "\t};"
            )

        # --- ADXCVR overlay nodes ---
        for lk in links:
            is_rx = lk.direction == "rx"
            gt_prefix = "rx" if is_rx else "tx"
            nodes.append(
                self._render(
                    "adxcvr.tmpl",
                    {
                        "label": lk.xcvr_label,
                        "sys_clk_select": lk.sys_clk_select,
                        "out_clk_select": lk.out_clk_select,
                        "clk_ref": f"hmc7044 {fpga_refclk_channel}",
                        "use_div40": False,
                        "div40_clk_ref": None,
                        "clock_output_names_str": f'"{gt_prefix}{lk.variant}_gt_clk", "{gt_prefix}{lk.variant}_out_clk"',
                        "use_lpm_enable": False,
                        "jesd_l": None,
                        "jesd_m": None,
                        "jesd_s": None,
                        "jesd204_inputs": f"hmc7044 0 {lk.link_id}",
                        "is_rx": is_rx,
                    },
                )
            )

        # --- TPL core overlay nodes ---
        ad9084_spi_label = "trx0_ad9084"
        for lk in links:
            # TX TPL cores need sampl_clk from the AD9084 converter
            if lk.direction == "tx":
                sampl_clk_ref = f"{ad9084_spi_label} 1"
                sampl_clk_name = "sampl_clk"
            else:
                sampl_clk_ref = None
                sampl_clk_name = None
            nodes.append(
                self._render(
                    "tpl_core.tmpl",
                    {
                        "label": lk.tpl_label,
                        "compatible": lk.tpl_compatible,
                        "direction": lk.direction,
                        "dma_label": lk.dma_label,
                        "spibus_label": ad9084_spi_label,
                        "jesd_label": lk.jesd_label,
                        "jesd_link_offset": 0,
                        "link_id": lk.link_id,
                        "pl_fifo_enable": lk.direction == "tx",
                        "sampl_clk_ref": sampl_clk_ref,
                        "sampl_clk_name": sampl_clk_name,
                    },
                )
            )

        # --- JESD204 overlay nodes ---
        for lk in links:
            # Pick per-link device_clk from HMC7044 channels
            if lk.direction == "rx":
                dev_label = rx_dev_clk_label
                dev_idx = rx_b_dev_clk_index if lk.variant else rx_dev_clk_index
            else:
                dev_label = tx_dev_clk_label
                dev_idx = tx_b_dev_clk_index if lk.variant else tx_dev_clk_index

            # 4-clock format: s_axi_aclk, link_clk, device_clk, lane_clk
            axi_clk = (
                f"<&{ps_clk_label}"
                + (f" {ps_clk_index}" if ps_clk_index is not None else "")
                + ">"
            )
            dev_idx_str = f" {dev_idx}" if dev_idx is not None else ""
            clocks_str = (
                f"{axi_clk}, <&{lk.xcvr_label} 1>, "
                f"<&{dev_label}{dev_idx_str}>, <&{lk.xcvr_label} 0>"
            )

            f_val = rx_f if lk.direction == "rx" else tx_f
            k_val = rx_k if lk.direction == "rx" else tx_k

            nodes.append(
                self._render(
                    "jesd204_overlay.tmpl",
                    {
                        "label": lk.jesd_label,
                        "direction": lk.direction,
                        "clocks_str": clocks_str,
                        "clock_names_str": '"s_axi_aclk", "link_clk", "device_clk", "lane_clk"',
                        "clock_output_name": None,
                        "f": f_val,
                        "k": k_val,
                        "jesd204_inputs": f"{lk.xcvr_label} 0 {lk.link_id}",
                        "converter_resolution": None,
                        "converters_per_device": None,
                        "bits_per_sample": None,
                        "control_bits_per_sample": None,
                    },
                )
            )

        # --- HMC7044 clock chip SPI node ---
        hmc7044_clock_output_names = [f"hmc7044_out{i}" for i in range(14)]

        # Default channel configuration for AD9084 VCU118
        custom_hmc7044_blocks = board_cfg.get("hmc7044_channel_blocks")
        if custom_hmc7044_blocks:
            raw_channels = "".join(
                self._format_nested_block(str(block)) for block in custom_hmc7044_blocks
            )
            hmc7044_channels = None
        else:
            raw_channels = None
            hmc7044_channels = self._build_hmc7044_channel_ctx(
                pll2_output_hz,
                board_cfg.get(
                    "hmc7044_channels",
                    [
                        {
                            "id": 1,
                            "name": "ADF4030_REFIN",
                            "divider": 20,
                            "driver_mode": 2,
                        },
                        {
                            "id": 3,
                            "name": "ADF4030_BSYNC0",
                            "divider": 256,
                            "driver_mode": 2,
                            "is_sysref": True,
                        },
                        {
                            "id": 8,
                            "name": "CORE_CLK_TX",
                            "divider": 8,
                            "driver_mode": 2,
                        },
                        {
                            "id": 9,
                            "name": "CORE_CLK_RX",
                            "divider": 8,
                            "driver_mode": 2,
                        },
                        {
                            "id": 10,
                            "name": "FPGA_REFCLK",
                            "divider": 8,
                            "driver_mode": 2,
                        },
                        {
                            "id": 11,
                            "name": "CORE_CLK_RX_B",
                            "divider": 8,
                            "driver_mode": 2,
                        },
                        {
                            "id": 12,
                            "name": "CORE_CLK_TX_B",
                            "divider": 8,
                            "driver_mode": 2,
                        },
                        {
                            "id": 13,
                            "name": "FPGA_SYSREF",
                            "divider": 256,
                            "driver_mode": 2,
                            "is_sysref": True,
                        },
                    ],
                ),
            )

        hmc7044_ctx = self._build_hmc7044_ctx(
            label="hmc7044",
            cs=hmc7044_cs,
            spi_max_hz=int(board_cfg.get("hmc7044_spi_max_hz", 1_000_000)),
            pll1_clkin_frequencies=board_cfg.get(
                "pll1_clkin_frequencies", [vcxo_hz, 10_000_000, 0, 0]
            ),
            vcxo_hz=vcxo_hz,
            pll2_output_hz=pll2_output_hz,
            clock_output_names=hmc7044_clock_output_names,
            channels=hmc7044_channels,
            raw_channels=raw_channels,
            jesd204_sysref_provider=True,
            jesd204_max_sysref_hz=int(
                board_cfg.get("jesd204_max_sysref_hz", 2_000_000)
            ),
            pll1_loop_bandwidth_hz=int(board_cfg.get("pll1_loop_bandwidth_hz", 200)),
            pll1_ref_prio_ctrl=board_cfg.get("pll1_ref_prio_ctrl", "0xE1"),
            pll1_ref_autorevert=board_cfg.get("pll1_ref_autorevert", True),
            pll1_charge_pump_ua=int(board_cfg.get("pll1_charge_pump_ua", 720)),
            pfd1_max_freq_hz=int(board_cfg.get("pfd1_max_freq_hz", 1_000_000)),
            sysref_timer_divider=int(board_cfg.get("sysref_timer_divider", 1024)),
            pulse_generator_mode=int(board_cfg.get("pulse_generator_mode", 0)),
            clkin0_buffer_mode=board_cfg.get("clkin0_buffer_mode", "0x07"),
            clkin1_buffer_mode=board_cfg.get("clkin1_buffer_mode", "0x07"),
            oscin_buffer_mode=board_cfg.get("oscin_buffer_mode", "0x15"),
            gpi_controls=board_cfg.get("gpi_controls", [0x00, 0x00, 0x00, 0x00]),
            gpo_controls=board_cfg.get("gpo_controls", [0x37, 0x33, 0x00, 0x00]),
            clkin0_ref="clkin_125" if board_cfg.get("adf4382_cs") is not None else None,
        )
        # --- ADF4382 PLL SPI node (provides dev_clk to AD9084) ---
        adf4382_cs = board_cfg.get("adf4382_cs")
        if adf4382_cs is not None:
            adf4382_freq = int(
                clock_cfg.get("adf4382_output_frequency", 20_000_000_000)
            )
            adf4382_node = (
                "\t\tadf4382: adf4382@{cs} {{\n"
                "\t\t\t#clock-cells = <1>;\n"
                '\t\t\tcompatible = "adi,adf4382";\n'
                "\t\t\treg = <{cs}>;\n"
                "\t\t\tspi-max-frequency = <1000000>;\n"
                "\t\t\tadi,spi-3wire-enable;\n"
                "\t\t\tclocks = <&hmc7044 1>;\n"
                '\t\t\tclock-names = "ref_clk";\n'
                '\t\t\tclock-output-names = "adf4382_out_clk";\n'
                "\t\t\tadi,power-up-frequency = /bits/ 64 <{freq}>;\n"
                '\t\t\tlabel = "adf4382";\n'
                "\t\t\t#io-channel-cells = <1>;\n"
                "\t\t}};\n"
            ).format(cs=int(adf4382_cs), freq=adf4382_freq)
            # Fixed 125MHz reference clock for ADF4382/HMC7044.
            # Inline as a bus-level node so it lands inside &amba_pl.
            nodes.append(
                "\tclkin_125: clock@0 {\n"
                "\t\t#clock-cells = <0>;\n"
                '\t\tcompatible = "fixed-clock";\n'
                "\t\tclock-frequency = <125000000>;\n"
                '\t\tclock-output-names = "clkin_125";\n'
                "\t};"
            )

        # Add clkin0 reference to HMC7044 SPI bus wrapper
        hmc7044_spi_children = self._render("hmc7044.tmpl", hmc7044_ctx)
        if adf4382_cs is not None:
            nodes.append(
                self._wrap_spi_bus(clock_spi, hmc7044_spi_children + adf4382_node)
            )
        else:
            nodes.append(self._wrap_spi_bus(clock_spi, hmc7044_spi_children))

        # --- HSCI overlay node ---
        hsci_label = board_cfg.get("hsci_label")
        if hsci_label:
            hsci_speed = int(board_cfg.get("hsci_speed_mhz", 800))
            # The clkgen label used for HSCI pclk
            hsci_clk_label = next(
                (c.name.replace("-", "_") for c in topology.clkgens),
                "axi_hsci_clkgen",
            )
            nodes.append(
                f"\t&{hsci_label} {{\n"
                '\t\tcompatible = "adi,axi-hsci-1.0.a";\n'
                f"\t\tclocks = <&{hsci_clk_label} 0>;\n"
                '\t\tclock-names = "pclk";\n'
                f"\t\tadi,hsci-interface-speed-mhz = <{hsci_speed}>;\n"
                "\t};"
            )

        # --- AD9084 converter SPI node ---
        # Build jesd204-inputs linking to all TPL cores
        tpl_inputs = []
        all_link_ids = []
        for lk in links:
            tpl_inputs.append(f"<&{lk.tpl_label} 0 {lk.link_id}>")
            all_link_ids.append(str(lk.link_id))

        # dev_clk source: ADF4382 or HMC7044
        dev_clk_ref = board_cfg.get("dev_clk_ref")
        if not dev_clk_ref:
            dev_clk_ref = f"hmc7044 {int(board_cfg.get('dev_clk_channel', 9))}"
        dev_clk_scales = board_cfg.get("dev_clk_scales")

        ad9084_ctx = {
            "label": ad9084_spi_label,
            "cs": converter_cs,
            "spi_max_hz": int(board_cfg.get("converter_spi_max_hz", 1_000_000)),
            "gpio_label": gpio_label,
            "reset_gpio": reset_gpio,
            "dev_clk_ref": dev_clk_ref,
            "dev_clk_scales": dev_clk_scales,
            "firmware_name": firmware_name,
            "subclass": board_cfg.get("subclass", 0),
            "side_b_separate_tpl": bool(board_cfg.get("side_b_separate_tpl", True)),
            "jrx0_physical_lane_mapping": board_cfg.get("jrx0_physical_lane_mapping"),
            "jtx0_logical_lane_mapping": board_cfg.get("jtx0_logical_lane_mapping"),
            "jrx1_physical_lane_mapping": board_cfg.get("jrx1_physical_lane_mapping"),
            "jtx1_logical_lane_mapping": board_cfg.get("jtx1_logical_lane_mapping"),
            "hsci_label": hsci_label,
            "hsci_auto_linkup": bool(board_cfg.get("hsci_auto_linkup", False)),
            "link_ids": " ".join(all_link_ids),
            "jesd204_inputs": ", ".join(tpl_inputs),
        }
        nodes.append(
            self._wrap_spi_bus(converter_spi, self._render("ad9084.tmpl", ad9084_ctx))
        )

        return nodes

    def _build_adrv9009_nodes(
        self, topology: XsaTopology, cfg: dict[str, Any]
    ) -> list[str]:
        """Build DTS node strings for an ADRV9009/9025 transceiver design.

        Handles both standard single-chip and dual-chip FMComms8 layouts using
        Jinja2 templates for the clock chip, PHY device, and JESD204 overlay nodes.
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
            hmc7044_clock_output_names = [
                "hmc7044_fmc_out0_DEV_REFCLK_C",
                "hmc7044_fmc_out1_DEV_SYSREF_C",
                "hmc7044_fmc_out2_DEV_REFCLK_D",
                "hmc7044_fmc_out3_DEV_SYSREF_D",
                "hmc7044_fmc_out4_JESD_REFCLK_TX_OBS_CD",
                "hmc7044_fmc_out5_JESD_REFCLK_RX_CD",
                "hmc7044_fmc_out6_FPGA_SYSREF_TX_OBS_CD",
                "hmc7044_fmc_out7_FPGA_SYSREF_RX_CD",
                "hmc7044_fmc_out8_CORE_CLK_TX_OBS_CD",
                "hmc7044_fmc_out9_CORE_CLK_RX_CD",
                "hmc7044_fmc_out10",
                "hmc7044_fmc_out11",
                "hmc7044_fmc_out12",
                "hmc7044_fmc_out13",
            ]
            custom_clock_chip_blocks = board_cfg.get("hmc7044_channel_blocks")
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
            custom_clock_chip_blocks = board_cfg.get("ad9528_channel_blocks")
            trx2_cs = None
            trx2_reset_gpio = None
            trx1_clocks = trx_clocks

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

        # --- Build clock chip node via template ---
        if is_fmcomms8_layout:
            if custom_clock_chip_blocks:
                raw_channels_block = "".join(
                    self._format_nested_block(str(block))
                    for block in custom_clock_chip_blocks
                )
            else:
                raw_channels_block = default_clock_chip_channels_block
            hmc7044_ctx = self._build_hmc7044_ctx(
                label=clock_chip_label,
                cs=clk_cs,
                spi_max_hz=10000000,
                pll1_clkin_frequencies=hmc7044_pll1_clkin_freqs,
                vcxo_hz=hmc7044_vcxo_freq,
                pll2_output_hz=hmc7044_pll2_out_freq,
                clock_output_names=hmc7044_clock_output_names,
                channels=None,
                raw_channels=raw_channels_block,
                pll1_ref_prio_ctrl="0x1E",
                clkin0_buffer_mode="0x07",
                clkin1_buffer_mode="0x09",
                clkin2_buffer_mode="0x05",
                clkin3_buffer_mode="0x11",
                oscin_buffer_mode="0x15",
                pll1_loop_bandwidth_hz=200,
                sync_pin_mode=1,
                pulse_generator_mode=7,
                sysref_timer_divider=3840,
                high_perf_mode_dist_enable=True,
                gpi_controls=hmc7044_gpi_controls,
                gpo_controls=hmc7044_gpo_controls,
            )
            clock_chip_node = self._render("hmc7044.tmpl", hmc7044_ctx)
        else:
            if custom_clock_chip_blocks:
                # When custom channel blocks are provided, inject them inline.
                # ad9528_1.tmpl only supports structured channel dicts, so we
                # construct the clock chip node manually to preserve the raw blocks.
                custom_channels_block = "".join(
                    self._format_nested_block(str(block))
                    for block in custom_clock_chip_blocks
                )
                _vcxo = ad9528_vcxo_freq or int(
                    board_cfg.get("ad9528_vcxo_freq", 122880000)
                )
                _clock_output_names = (
                    '"ad9528-1_out0", "ad9528-1_out1", "ad9528-1_out2", '
                    '"ad9528-1_out3", "ad9528-1_out4", "ad9528-1_out5", '
                    '"ad9528-1_out6", "ad9528-1_out7", "ad9528-1_out8", '
                    '"ad9528-1_out9", "ad9528-1_out10", "ad9528-1_out11", '
                    '"ad9528-1_out12", "ad9528-1_out13";'
                )
                clock_chip_node = (
                    f"\t\t{clock_chip_label}: ad9528-1@{clk_cs} {{\n"
                    '\t\t\tcompatible = "adi,ad9528";\n'
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
                    f"\t\t\tadi,vcxo-freq = <{_vcxo}>;\n"
                    f"\t\t\tclock-output-names = {_clock_output_names}\n"
                    f"\t\t\t#clock-cells = <1>;\n"
                    f"{custom_channels_block}"
                    "\t\t};\n"
                )
            else:
                ad9528_ctx = self._build_ad9528_1_ctx(board_cfg)
                clock_chip_node = self._render("ad9528_1.tmpl", ad9528_ctx)

        # --- Build PHY device node via template ---
        phy_ctx = self._build_adrv9009_device_ctx(
            phy_family=phy_family,
            phy_compatible=phy_compatible,
            trx_cs=trx_cs,
            trx_spi_max_frequency=trx_spi_max_frequency,
            gpio_label=gpio_label,
            trx_reset_gpio=trx_reset_gpio,
            trx_sysref_req_gpio=trx_sysref_req_gpio,
            trx_clocks_value=trx_clocks_value,
            trx_clock_names_value=trx_clock_names_value,
            trx_link_ids_value=trx_link_ids_value,
            trx_inputs_value=trx_inputs_value,
            trx_profile_props_block=trx_profile_props_block,
            is_fmcomms8=is_fmcomms8_layout,
            trx2_cs=trx2_cs if is_fmcomms8_layout else None,
            trx2_reset_gpio=trx2_reset_gpio if is_fmcomms8_layout else None,
            trx1_clocks_value=trx1_clocks_value if is_fmcomms8_layout else None,
        )
        phy_node = self._render("adrv9009.tmpl", phy_ctx)

        # --- Wrap clock chip + PHY in SPI bus overlay ---
        spi_node = self._wrap_spi_bus(spi_bus, clock_chip_node + phy_node)

        # --- Build JESD overlay nodes via template ---
        rx_jesd_ctx = {
            "label": rx_jesd_label,
            "direction": "rx",
            "clocks_str": f"<&{ps_clk_label} {ps_clk_index}>, {rx_device_clk_ref}, <&{rx_xcvr_label} 0>",
            "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
            "clock_output_name": None,
            "f": rx_f,
            "k": rx_k,
            "jesd204_inputs": f"{rx_xcvr_label} 0 {rx_link_id}",
            "converter_resolution": None,
            "converters_per_device": None,
            "bits_per_sample": None,
            "control_bits_per_sample": None,
        }
        tx_jesd_ctx = {
            "label": tx_jesd_label,
            "direction": "tx",
            "clocks_str": f"<&{ps_clk_label} {ps_clk_index}>, {tx_device_clk_ref}, <&{tx_xcvr_label} 0>",
            "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
            "clock_output_name": None,
            "f": tx_octets_per_frame,
            "k": tx_k,
            "jesd204_inputs": f"{tx_xcvr_label} 0 {tx_link_id}",
            "converter_resolution": 14,
            "converters_per_device": tx_m,
            "bits_per_sample": 16,
            "control_bits_per_sample": 2,
        }

        # --- Build XCVR overlay nodes as raw f-strings (no sys_clk_select/out_clk_select) ---
        rx_xcvr_node = (
            f"\t&{rx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {rx_xcvr_conv_clk_ref}, {rx_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_gt_clk", "rx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};"
        )
        rx_os_xcvr_node = (
            f"\t&{rx_os_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {rx_os_xcvr_conv_clk_ref}, {rx_os_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_os_gt_clk", "rx_os_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};"
        )
        tx_xcvr_node = (
            f"\t&{tx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = {tx_xcvr_conv_clk_ref}, {tx_xcvr_div40_ref};\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "tx_gt_clk", "tx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};"
        )

        # --- Build DMA nodes ---
        def _dma_node(label: str) -> str:
            return (
                f"\t&{label} {{\n"
                '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
                "\t\t#dma-cells = <1>;\n"
                "\t\t#clock-cells = <0>;\n"
                "\t};"
            )

        # --- Build TPL core nodes (first pass: compatible + dmas, no spibus-connected) ---
        phy_label = f"trx0_{phy_family}"
        rx_core_first = (
            f"\t&{rx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-rx-1.0";\n'
            "\t\tadi,axi-decimation-core-available;\n"
            f"\t\tdmas = <&{rx_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t};"
        )
        rx_os_core_first = (
            f"\t&{rx_os_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-obs-1.0";\n'
            f"\t\tdmas = <&{rx_os_dma_label} 0>;\n"
            '\t\tdma-names = "rx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )
        tx_core_first = (
            f"\t&{tx_core_label} {{\n"
            '\t\tcompatible = "adi,axi-adrv9009-tx-1.0";\n'
            "\t\tadi,axi-interpolation-core-available;\n"
            f"\t\tdmas = <&{tx_dma_label} 0>;\n"
            '\t\tdma-names = "tx";\n'
            f"\t\tclocks = <&{ps_clk_label} {ps_clk_index}>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )

        # --- Build TPL core second pass (spibus-connected + phy clock references) ---
        rx_core_second = (
            f"\t&{rx_core_label} {{\n\t\tspibus-connected = <&{phy_label}>;\n\t}};"
        )
        rx_os_core_second = (
            f"\t&{rx_os_core_label} {{\n"
            f"\t\tclocks = <&{phy_label} 1>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )
        tx_core_second = (
            f"\t&{tx_core_label} {{\n"
            f"\t\tspibus-connected = <&{phy_label}>;\n"
            f"\t\tclocks = <&{phy_label} 2>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};"
        )

        nodes = [
            "\t&misc_clk_0 {\n"
            '\t\tcompatible = "fixed-clock";\n'
            "\t\t#clock-cells = <0>;\n"
            f"\t\tclock-frequency = <{misc_clk_hz}>;\n"
            "\t};",
            self._render("jesd204_overlay.tmpl", rx_jesd_ctx),
            self._render("jesd204_overlay.tmpl", tx_jesd_ctx),
            _dma_node(rx_dma_label),
            _dma_node(tx_dma_label),
            _dma_node(rx_os_dma_label),
            rx_xcvr_node,
            rx_os_xcvr_node,
            tx_xcvr_node,
            rx_core_first,
            rx_os_core_first,
            tx_core_first,
            spi_node,
            rx_core_second,
            rx_os_core_second,
            tx_core_second,
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
            rx_os_jesd_ctx = {
                "label": rx_os_jesd_label,
                "direction": "rx",
                "clocks_str": f"<&{ps_clk_label} {ps_clk_index}>, {rx_os_device_clk_ref}, <&{rx_os_xcvr_label} 0>",
                "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
                "clock_output_name": None,
                "f": rx_os_octets_per_frame,
                "k": rx_k,
                "jesd204_inputs": f"{rx_os_xcvr_label} 0 {rx_os_link_id}",
                "converter_resolution": None,
                "converters_per_device": None,
                "bits_per_sample": None,
                "control_bits_per_sample": None,
            }
            nodes.insert(
                4 if has_rx_clkgen and has_tx_clkgen and has_rx_os_clkgen else 3,
                self._render("jesd204_overlay.tmpl", rx_os_jesd_ctx),
            )
        return nodes
