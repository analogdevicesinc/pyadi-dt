"""Independent ADRV9040 builder for standard and ORX/NLS ZCU102 designs."""

from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar

from pydantic import Field

from ....devices._dt_render import render_node
from ....devices._fields import DtSkip
from ....devices.clocks import AD9528_1, AD9528_1Channel
from ....devices.fpga_ip import Adxcvr, Jesd204Overlay, TplCore
from ....devices.transceivers import ADRV9040
from ...config.board_configs import ADRV9040BoardConfig
from ...parse.topology import AxiIpInstance, XsaTopology


def _label(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _path(name: str) -> str | None:
    lower = _label(name).lower()
    if re.search(r"(?:^|_)(?:rx_os|orx|obs)(?:_|$)", lower):
        return "rx_os"
    if re.search(r"(?:^|_)tx(?:_|$)", lower):
        return "tx"
    if re.search(r"(?:^|_)rx(?:_|$)", lower):
        return "rx"
    return None


class _Channel(AD9528_1Channel):
    """AD9528 output with the reference REF_CLK0 disable flag."""

    output_disabled: bool = Field(False, alias="adi,output-dis")


class _Clock(AD9528_1):
    """Clock settings from Linux 22534a028813, independent of Talise wiring."""

    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#clock-cells": 1,
        "adi,refa-r-div": 1,
        "adi,pll1-feedback-div": 4,
        "adi,pll1-charge-pump-current-nA": 5000,
        "adi,pll2-vco-div-m1": 4,
        "adi,pll2-n2-div": 4,
        "adi,pll2-r1-div": 1,
        "adi,pll2-charge-pump-current-nA": 815000,
        "adi,sysref-src": 2,
        "adi,sysref-pattern-mode": 0,
        "adi,sysref-k-div": 512,
        "adi,sysref-nshot-mode": 5,
        "adi,sysref-request-trigger-mode": 0,
        "adi,jesd204-desired-sysref-frequency-hz": 3840000,
        "adi,rpole2": 0,
        "adi,rzero": 7,
        "adi,cpole1": 2,
        "adi,status-mon-pin0-function-select": 9,
        "adi,status-mon-pin1-function-select": 3,
    }
    dt_flags: ClassVar[tuple[str, ...]] = (
        "adi,refa-enable",
        "adi,refa-diff-rcv-enable",
        "adi,pll2-freq-doubler-enable",
    )
    reset_gpio: Annotated[int | None, DtSkip()] = 147

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        lines = super().extra_dt_lines(context)
        if self.reset_gpio is not None:
            gpio = (context or {}).get("gpio_label", "gpio")
            lines.append(f"reset-gpios = <&{gpio} {self.reset_gpio} 1>;")
        return lines


def _ip_node(ip: AxiIpInstance, body: str) -> str:
    """Render a complete addressed node using the XSA register window."""
    if ip.base_addr <= 0 or ip.size <= 0:
        raise ValueError(f"incomplete register range for {ip.name}")
    if ip.ip_type == "axi_adxcvr":
        body = "\t\t#address-cells = <1>;\n\t\t#size-cells = <0>;\n" + body
    return (
        f"\t{_label(ip.name)}: {ip.ip_type.replace('_', '-')}@{ip.base_addr:x} {{\n"
        f"\t\treg = <0x0 0x{ip.base_addr:x} 0x0 0x{ip.size:x}>;\n" + body + "\n\t};"
    )


def _model_node(ip: AxiIpInstance, model: Any) -> str:
    """Reuse the FPGA models while rendering full nodes rather than overlays."""
    rendered = render_node(
        model, label=_label(ip.name), node_name="unused", indent="\t"
    )
    return _ip_node(ip, rendered[rendered.index("\n") + 1 : rendered.rindex("\n")])


class ADRV9040Builder:
    """Render every addressed block in the ADRV9040 JESD datapaths."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        """Recognize ADRV9040/ADRV904x handoffs or explicitly requested wiring."""
        return topology.is_adrv9040_design() or "adrv9040_board" in cfg

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        """Validate complete chains, then render PHY, clocks and FPGA nodes."""
        if topology.inferred_platform() != "zcu102":
            raise ValueError("ADRV9040 wiring is supported only for ZCU102")
        board = ADRV9040BoardConfig.from_dict(cfg.get("adrv9040_board", {}))
        observation = topology.has_adrv9040_observation()
        if board.observation is not None and board.observation != observation:
            raise ValueError(
                "ADRV9040 profile observation setting does not match XSA topology"
            )
        paths = ("rx", "tx", "rx_os") if observation else ("rx", "tx")
        roles = {
            "jesd": {"axi_jesd204_rx", "axi_jesd204_tx"},
            "clkgen": {"axi_clkgen"},
            "xcvr": {"axi_adxcvr"},
            "dma": {"axi_dmac"},
            "tpl": {
                "ad_ip_jesd204_tpl_adc",
                "ad_ip_jesd204_tpl_dac",
                "axi_adrv9040",
                "axi_adrv904x",
            },
        }
        chains: dict[str, dict[str, AxiIpInstance]] = {}
        for path in paths:
            chain = {}
            for role, types in roles.items():
                candidates = [
                    ip
                    for ip in topology.ip_instances
                    if ip.ip_type in types
                    and _path(ip.name) == path
                    and re.search(r"adrv904[0x]", ip.name.lower())
                ]
                if len(candidates) != 1:
                    raise ValueError(
                        f"incomplete ADRV9040 {path} chain: missing or ambiguous {role}"
                    )
                chain[role] = candidates[0]
            expected_direction = "tx" if path == "tx" else "rx"
            if chain["jesd"].ip_type != f"axi_jesd204_{expected_direction}":
                raise ValueError(
                    f"incomplete ADRV9040 {path} chain: incorrect JESD direction"
                )
            for role in ("dma", "jesd"):
                if chain[role].irq is None:
                    raise ValueError(
                        f"incomplete interrupt route for {chain[role].name}"
                    )
            chains[path] = chain

        # Data-offload names need not contain the transceiver family name.
        offloads = [
            ip for ip in topology.ip_instances if ip.ip_type == "axi_data_offload"
        ]
        tx_offloads = [ip for ip in offloads if _path(ip.name) == "tx"]
        if len(tx_offloads) > 1:
            raise ValueError("ambiguous ADRV9040 TX data-offload")
        ps_ref = (
            f"<&{ps_clk_label} {ps_clk_index}>"
            if ps_clk_index is not None
            else f"<&{ps_clk_label}>"
        )
        nodes: list[str] = []
        channels = board.ad9528_channels
        if channels is None:
            channels = [
                {
                    "id": index,
                    "name": name,
                    "divider": divider,
                    "signal_source": source,
                    "output_disabled": index == 13,
                }
                for index, name, divider, source in (
                    (0, "DEV_SYSREF", 4, 2),
                    (1, "DEV_CLK", 4, 0),
                    (3, "CORE_CLK", 4, 0),
                    (11, "REF_CLK1", 2, 2),
                    (12, "FPGA_SYSREF", 4, 2),
                    (13, "REF_CLK0", 2, 0),
                )
            ]
        channel_models = [_Channel(**ch) for ch in channels]
        if len({ch.id for ch in channel_models}) != len(channel_models) or not {
            1,
            3,
            13,
        }.issubset(ch.id for ch in channel_models):
            raise ValueError(
                "ADRV9040 clock channels must be unique and include 1, 3 and 13"
            )
        clock = _Clock(
            label="clk0_ad9528",
            reset_gpio=board.clock_reset_gpio,
            vcxo_hz=board.ad9528_vcxo_hz,
            jesd204_sysref_provider=True,
            channels={ch.id: ch for ch in channel_models},
        )
        phy_fields = (
            "arm_firmware_name",
            "arm_dfe_firmware_name",
            "stream_firmware_name",
            "rx_gaintable_names",
            "rx_gaintable_channel_masks",
            "tx_attntable_names",
            "tx_attntable_channel_masks",
            "reset_gpio",
            "interrupt_gpio",
            "sysref_req_gpio",
        )
        phy = ADRV9040(
            **{key: getattr(board, key) for key in phy_fields},
            observation=observation,
            spi_max_hz=board.spi_max_frequency,
            ignore_jesd_errors=board.ignore_jesd_errors,
            device_config_name=board.device_config_name
            or (
                "DeviceProfileTest_NLS.bin" if observation else "DeviceProfileTest.bin"
            ),
        )
        phy_inputs = [
            f"<&{_label(chains['tx']['tpl'].name)} 0 0>",
            f"<&{_label(chains['rx']['jesd'].name)} 0 2>",
        ]
        if observation:
            phy_inputs.append(f"<&{_label(chains['rx_os']['jesd'].name)} 0 3>")
        children = (
            clock.render_dt(cs=board.clock_cs, context={"gpio_label": gpio_label})
            + "\n"
            + phy.render_dt(
                cs=board.trx_cs,
                context={
                    "gpio_label": gpio_label,
                    "dev_clk_ref": "clk0_ad9528 1",
                    "jesd204_inputs": ", ".join(phy_inputs),
                },
            )
        )
        nodes.append(node_builder._wrap_spi_bus(board.spi_bus, children))
        for path, chain in chains.items():
            tx = path == "tx"
            direction = "tx" if tx else "rx"
            link_id = {"tx": 0, "rx": 2, "rx_os": 3}[path]
            sample_index = {"tx": 1, "rx": 0, "rx_os": 2}[path]
            dma, jesd, clkgen, xcvr, tpl = (
                chain[key] for key in ("dma", "jesd", "clkgen", "xcvr", "tpl")
            )
            dma_body = (
                '\t\tcompatible = "adi,axi-dmac-1.00.a";\n\t\t#dma-cells = <1>;\n\t\t#clock-cells = <0>;\n'
                f"\t\tinterrupt-parent = <&gic>;\n\t\tinterrupts = <0 {dma.irq} 4>;\n\t\tclocks = <&{ps_clk_label} 73>;"
            )
            if int(dma.parameters.get("CACHE_COHERENT", "0"), 0):
                dma_body += "\n\t\tdma-coherent;"
            nodes.append(_ip_node(dma, dma_body))
            nodes.append(
                _ip_node(
                    clkgen,
                    '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n\t\t#clock-cells = <0>;\n'
                    f'\t\tclocks = <&clk0_ad9528 3>, {ps_ref};\n\t\tclock-names = "clkin1", "s_axi_aclk";\n\t\tclock-output-names = "{_label(clkgen.name)}";',
                )
            )
            nodes.append(
                _model_node(
                    xcvr,
                    Adxcvr(
                        label=_label(xcvr.name),
                        sys_clk_select=int(xcvr.parameters.get("SYS_CLK_SEL", "3"), 0),
                        out_clk_select=int(xcvr.parameters.get("OUT_CLK_SEL", "3"), 0),
                        clk_ref="clk0_ad9528 13",
                        clock_output_names_str=f'"{path}_gt_clk", "{path}_out_clk"',
                        jesd204_inputs=f"clk0_ad9528 0 {link_id}",
                    ),
                )
            )
            params = cfg.get("jesd", {}).get(path, {})
            jesd_node = _model_node(
                jesd,
                Jesd204Overlay(
                    label=_label(jesd.name),
                    compatible_str=f"adi,axi-jesd204-{direction}-1.0",
                    f=int(params.get("F", 4)),
                    k=int(params.get("K", 32)),
                    clocks_str=f"{ps_ref}, <&{_label(clkgen.name)}>, <&{_label(xcvr.name)} 0>",
                    clock_names_str='"s_axi_aclk", "device_clk", "lane_clk"',
                    clock_output_name=f"jesd_{path}_lane_clk",
                    jesd204_inputs=f"{_label(xcvr.name)} 0 {link_id}",
                ),
            )
            nodes.append(
                jesd_node.replace(
                    "\n\t};",
                    f"\n\t\tinterrupt-parent = <&gic>;\n\t\tinterrupts = <0 {jesd.irq} 4>;\n\t}};",
                )
            )
            if tx:
                tpl_node = _model_node(
                    tpl,
                    TplCore(
                        label=_label(tpl.name),
                        compatible_str="adi,axi-adrv904x-tx-1.0",
                        direction="tx",
                        dma_label=_label(dma.name),
                        jesd_label=_label(jesd.name),
                        link_id=link_id,
                        sampl_clk_ref=f"trx0_adrv904x {sample_index}",
                        pl_fifo_enable=bool(tx_offloads),
                    ),
                )
                if tx_offloads:
                    tpl_node = tpl_node.replace(
                        "\n\t};",
                        f"\n\t\tadi,axi-data-offload-connected = <&{_label(tx_offloads[0].name)}>;\n\t}};",
                    )
            else:
                compatible = (
                    "adi,axi-adrv904x-obs-1.0"
                    if path == "rx_os"
                    else "adi,axi-adc-legacy-10.0.a"
                )
                tpl_node = _ip_node(
                    tpl,
                    f'\t\tcompatible = "{compatible}";\n\t\tdmas = <&{_label(dma.name)} 0>;\n\t\tdma-names = "rx";\n\t\tspibus-connected = <&trx0_adrv904x>;\n\t\tclocks = <&trx0_adrv904x {sample_index}>;\n\t\tclock-names = "sampl_clk";',
                )
            if path == "rx_os":
                tpl_node = tpl_node.replace(
                    "\n\t};", '\n\t\tlabel = "axi-adrv904x-rx-os-hpc";\n\t};'
                )
            nodes.append(tpl_node)
        nodes.extend(
            _ip_node(ip, '\t\tcompatible = "adi,axi-data-offload-1.0.a";')
            for ip in offloads
        )
        return nodes

    def skips_generic_jesd(self) -> bool:
        """Own the complete ADRV9040 clock and JESD chains."""
        return True

    def skip_ip_types(self) -> set[str]:
        """Suppress duplicate converter rendering by the generic builder."""
        return {"axi_adrv9040", "axi_adrv904x"}
