# adidt/xsa/node_builder.py
import os
import warnings
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .topology import XsaTopology, Jesd204Instance, ClkgenInstance, ConverterInstance


class NodeBuilder:
    """Builds ADI DTS node strings from XsaTopology + pyadi-jif JSON config."""

    def build(self, topology: XsaTopology, cfg: dict[str, Any]) -> dict[str, list[str]]:
        """Render ADI DTS nodes.

        Returns:
            Dict with keys "jesd204_rx", "jesd204_tx", "converters".
        """
        env = self._make_jinja_env()
        clock_map = self._build_clock_map(topology)
        result: dict[str, list[str]] = {
            "clkgens": [],
            "jesd204_rx": [],
            "jesd204_tx": [],
            "converters": [],
        }
        is_adrv9009_design = any(
            c.ip_type == "axi_adrv9009" or "adrv9009" in c.name.lower()
            for c in topology.converters
        )
        is_adrv9009_design = is_adrv9009_design or any(
            "adrv9009" in j.name.lower()
            for j in topology.jesd204_rx + topology.jesd204_tx
        )
        rx_labels: list[str] = []
        tx_labels: list[str] = []

        for clkgen in topology.clkgens:
            if is_adrv9009_design and "adrv9009" in clkgen.name.lower():
                continue
            result["clkgens"].append(self._render_clkgen(env, clkgen))

        for inst in topology.jesd204_rx:
            if is_adrv9009_design and "adrv9009" in inst.name.lower():
                continue
            clkgen_label, device_clk_label, device_clk_index = self._resolve_clock(
                inst, clock_map, cfg, "rx"
            )
            jesd_input_label, jesd_input_link_id = self._resolve_jesd_input(
                inst, cfg, "rx", clkgen_label
            )
            result["jesd204_rx"].append(
                self._render_jesd(
                    env,
                    inst,
                    cfg.get("jesd", {}).get("rx", {}),
                    clkgen_label,
                    device_clk_label,
                    device_clk_index,
                    jesd_input_label,
                    jesd_input_link_id,
                )
            )
            rx_labels.append(inst.name.replace("-", "_"))

        for inst in topology.jesd204_tx:
            if is_adrv9009_design and "adrv9009" in inst.name.lower():
                continue
            clkgen_label, device_clk_label, device_clk_index = self._resolve_clock(
                inst, clock_map, cfg, "tx"
            )
            jesd_input_label, jesd_input_link_id = self._resolve_jesd_input(
                inst, cfg, "tx", clkgen_label
            )
            result["jesd204_tx"].append(
                self._render_jesd(
                    env,
                    inst,
                    cfg.get("jesd", {}).get("tx", {}),
                    clkgen_label,
                    device_clk_label,
                    device_clk_index,
                    jesd_input_label,
                    jesd_input_link_id,
                )
            )
            tx_labels.append(inst.name.replace("-", "_"))

        for conv in topology.converters:
            rx_label = rx_labels[0] if rx_labels else "jesd_rx"
            tx_label = tx_labels[0] if tx_labels else "jesd_tx"
            result["converters"].append(
                self._render_converter(env, conv, rx_label, tx_label)
            )

        result["converters"].extend(self._build_adrv9009_nodes(topology, cfg))

        return result

    def _make_jinja_env(self) -> Environment:
        from .exceptions import XsaParseError

        loc = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "..", "templates", "xsa"
        )
        if not os.path.isdir(loc):
            raise XsaParseError(f"template directory not found: {loc}")
        return Environment(loader=FileSystemLoader(loc))

    def _build_clock_map(self, topology: XsaTopology) -> dict[str, ClkgenInstance]:
        return {net: cg for cg in topology.clkgens for net in cg.output_clks}

    def _resolve_clock(
        self,
        inst: Jesd204Instance,
        clock_map: dict[str, ClkgenInstance],
        cfg: dict[str, Any],
        direction: str,
    ) -> tuple[str, str, int]:
        clkgen = clock_map.get(inst.link_clk)
        if clkgen is None:
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
        env: Environment,
        inst: Jesd204Instance,
        jesd_params: dict[str, Any],
        clkgen_label: str,
        device_clk_label: str,
        device_clk_index: int,
        jesd_input_label: str,
        jesd_input_link_id: int,
    ) -> str:
        from .exceptions import ConfigError

        for key in ("F", "K"):
            if key not in jesd_params:
                raise ConfigError(f"jesd.{inst.direction}.{key}")
        return env.get_template("jesd204_fsm.tmpl").render(
            instance=inst,
            jesd=jesd_params,
            clkgen_label=clkgen_label,
            device_clk_label=device_clk_label,
            device_clk_index=device_clk_index,
            jesd_input_label=jesd_input_label,
            jesd_input_link_id=jesd_input_link_id,
        )

    def _render_converter(
        self, env: Environment, conv: ConverterInstance, rx_label: str, tx_label: str
    ) -> str:
        from jinja2 import TemplateNotFound

        try:
            tmpl = env.get_template(f"{conv.ip_type}.tmpl")
        except TemplateNotFound:
            return f"\t/* {conv.name}: no template for {conv.ip_type} */"
        return tmpl.render(
            instance=conv,
            rx_jesd_label=rx_label,
            tx_jesd_label=tx_label,
            spi_label="spi0",
            spi_cs=conv.spi_cs if conv.spi_cs is not None else 0,
        )

    def _render_clkgen(self, env: Environment, inst: ClkgenInstance) -> str:
        return env.get_template("clkgen.tmpl").render(instance=inst)

    def _build_adrv9009_nodes(
        self, topology: XsaTopology, cfg: dict[str, Any]
    ) -> list[str]:
        labels = {
            j.name.replace("-", "_") for j in topology.jesd204_rx + topology.jesd204_tx
        }
        if not any("adrv9009" in lbl for lbl in labels):
            return []
        rx_jesd_label = next(
            (
                lbl
                for lbl in labels
                if "_rx_jesd_rx_axi" in lbl and "_rx_os_" not in lbl
            ),
            next(
                (lbl for lbl in labels if "_rx_jesd" in lbl and "_rx_os_" not in lbl),
                None,
            ),
        )
        rx_os_jesd_label = next(
            (lbl for lbl in labels if "_rx_os_jesd_rx_axi" in lbl),
            next((lbl for lbl in labels if "_rx_os_jesd" in lbl), None),
        )
        tx_jesd_label = next(
            (lbl for lbl in labels if "_tx_jesd_tx_axi" in lbl),
            next((lbl for lbl in labels if "_tx_jesd" in lbl), None),
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

        trx_link_ids = ["1", "0"]
        trx_jesd_inputs = [f"<&{rx_xcvr_label} 0 1>", f"<&{tx_xcvr_label} 0 0>"]
        if rx_os_jesd_label:
            trx_link_ids.insert(1, "2")
            trx_jesd_inputs.insert(1, f"<&{rx_os_xcvr_label} 0 2>")
        trx_clocks = [
            "<&clk0_ad9528 13>",
            "<&clk0_ad9528 1>",
            "<&clk0_ad9528 12>",
            "<&clk0_ad9528 3>",
        ]
        trx_clock_names = [
            '"dev_clk"',
            '"fmc_clk"',
            '"sysref_dev_clk"',
            '"sysref_fmc_clk"',
        ]
        trx_clocks_value = ", ".join(trx_clocks)
        trx_clock_names_value = ", ".join(trx_clock_names)
        trx_link_ids_value = " ".join(trx_link_ids)
        trx_inputs_value = ", ".join(trx_jesd_inputs)

        nodes = [
            "\t&misc_clk_0 {\n"
            '\t\tcompatible = "fixed-clock";\n'
            "\t\t#clock-cells = <0>;\n"
            "\t\tclock-frequency = <245760000>;\n"
            "\t};",
            f"\t&{rx_clkgen_label} {{\n"
            '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
            "\t\t#clock-cells = <0>;\n"
            f'\t\tclock-output-names = "{rx_clkgen_label}";\n'
            '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
            "\t};",
            f"\t&{tx_clkgen_label} {{\n"
            '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
            "\t\t#clock-cells = <0>;\n"
            f'\t\tclock-output-names = "{tx_clkgen_label}";\n'
            '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
            "\t};",
            f"\t&{rx_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
            f"\t\tclocks = <&zynqmp_clk 71>, <&{rx_clkgen_label}>, <&{rx_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            f"\t\tadi,octets-per-frame = <{rx_f}>;\n"
            f"\t\tadi,frames-per-multiframe = <{rx_k}>;\n"
            f"\t\tjesd204-inputs = <&{rx_xcvr_label} 0 1>;\n"
            "\t};",
            f"\t&{tx_jesd_label} {{\n"
            '\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n'
            f"\t\tclocks = <&zynqmp_clk 71>, <&{tx_clkgen_label}>, <&{tx_xcvr_label} 0>;\n"
            '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
            "\t\t#clock-cells = <0>;\n"
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t\tadi,octets-per-frame = <2>;\n"
            f"\t\tadi,frames-per-multiframe = <{tx_k}>;\n"
            "\t\tadi,converter-resolution = <14>;\n"
            "\t\tadi,bits-per-sample = <16>;\n"
            f"\t\tadi,converters-per-device = <{tx_m}>;\n"
            "\t\tadi,control-bits-per-sample = <2>;\n"
            f"\t\tjesd204-inputs = <&{tx_xcvr_label} 0 0>;\n"
            "\t};",
            "\t&axi_adrv9009_rx_dma {\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            "\t&axi_adrv9009_tx_dma {\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            "\t&axi_adrv9009_rx_os_dma {\n"
            '\t\tcompatible = "adi,axi-dmac-1.00.a";\n'
            "\t\t#dma-cells = <1>;\n"
            "\t\t#clock-cells = <0>;\n"
            "\t};",
            f"\t&{rx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&{rx_clkgen_label}>, <&{rx_clkgen_label}>;\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_gt_clk", "rx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
            f"\t&{rx_os_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&{rx_os_clkgen_label}>, <&{rx_os_clkgen_label}>;\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "rx_os_gt_clk", "rx_os_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
            f"\t&{tx_xcvr_label} {{\n"
            '\t\tcompatible = "adi,axi-adxcvr-1.0";\n'
            f"\t\tclocks = <&{tx_clkgen_label}>, <&{tx_clkgen_label}>;\n"
            '\t\tclock-names = "conv", "div40";\n'
            "\t\t#clock-cells = <1>;\n"
            '\t\tclock-output-names = "tx_gt_clk", "tx_out_clk";\n'
            "\t\tjesd204-device;\n"
            "\t\t#jesd204-cells = <2>;\n"
            "\t};",
            "\taxi_adrv9009_core_rx: axi-adrv9009-rx-hpc@84a00000 {\n"
            '\t\tcompatible = "adi,axi-adrv9009-rx-1.0";\n'
            "\t\treg = <0x0 0x84a00000 0x0 0x2000>;\n"
            "\t\tdmas = <&axi_adrv9009_rx_dma 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t\tadi,axi-decimation-core-available;\n"
            "\t};",
            "\taxi_adrv9009_core_rx_obs: axi-adrv9009-rx-obs-hpc@84a08000 {\n"
            '\t\tcompatible = "adi,axi-adrv9009-obs-1.0";\n'
            "\t\treg = <0x0 0x84a08000 0x0 0x1000>;\n"
            "\t\tdmas = <&axi_adrv9009_rx_os_dma 0>;\n"
            '\t\tdma-names = "rx";\n'
            "\t\tclocks = <&zynqmp_clk 71>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};",
            "\taxi_adrv9009_core_tx: axi-adrv9009-tx-hpc@84a04000 {\n"
            '\t\tcompatible = "adi,axi-adrv9009-tx-1.0";\n'
            "\t\treg = <0x0 0x84a04000 0x0 0x2000>;\n"
            "\t\tdmas = <&axi_adrv9009_tx_dma 0>;\n"
            '\t\tdma-names = "tx";\n'
            "\t\tclocks = <&zynqmp_clk 71>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t\tadi,axi-interpolation-core-available;\n"
            "\t};",
            "\t&spi0 {\n"
            '\t\tstatus = "okay";\n'
            "\t\tclk0_ad9528: ad9528-1@0 {\n"
            '\t\t\tcompatible = "adi,ad9528";\n'
            "\t\t\treg = <0>;\n"
            "\t\t\t#address-cells = <1>;\n"
            "\t\t\t#size-cells = <0>;\n"
            "\t\t\tspi-max-frequency = <10000000>;\n"
            '\t\t\tclock-output-names = "ad9528-1_out0", "ad9528-1_out1", "ad9528-1_out2", '
            '"ad9528-1_out3", "ad9528-1_out4", "ad9528-1_out5", "ad9528-1_out6", '
            '"ad9528-1_out7", "ad9528-1_out8", "ad9528-1_out9", "ad9528-1_out10", '
            '"ad9528-1_out11", "ad9528-1_out12", "ad9528-1_out13";\n'
            "\t\t\t#clock-cells = <1>;\n"
            "\t\t\tadi,vcxo-freq = <122880000>;\n"
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
            "\t\t\tad9528_0_c13: channel@13 {\n"
            "\t\t\t\treg = <13>;\n"
            '\t\t\t\tadi,extended-name = "DEV_CLK";\n'
            "\t\t\t\tadi,driver-mode = <0>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            "\t\t\t\tadi,channel-divider = <5>;\n"
            "\t\t\t\tadi,signal-source = <0>;\n"
            "\t\t\t};\n"
            "\t\t\tad9528_0_c1: channel@1 {\n"
            "\t\t\t\treg = <1>;\n"
            '\t\t\t\tadi,extended-name = "FMC_CLK";\n'
            "\t\t\t\tadi,driver-mode = <0>;\n"
            "\t\t\t\tadi,divider-phase = <0>;\n"
            "\t\t\t\tadi,channel-divider = <5>;\n"
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
            "\t\t};\n"
            "\t\ttrx0_adrv9009: adrv9009-phy@1 {\n"
            '\t\t\tcompatible = "adi,adrv9009", "adrv9009";\n'
            "\t\t\treg = <1>;\n"
            "\t\t\tspi-max-frequency = <25000000>;\n"
            f"\t\t\tclocks = {trx_clocks_value};\n"
            f"\t\t\tclock-names = {trx_clock_names_value};\n"
            "\t\t\t#clock-cells = <1>;\n"
            '\t\t\tclock-output-names = "rx_sampl_clk", "rx_os_sampl_clk", "tx_sampl_clk";\n'
            "\t\t\treset-gpios = <&gpio 130 0>;\n"
            "\t\t\tsysref-req-gpios = <&gpio 136 0>;\n"
            "\t\t\tjesd204-device;\n"
            "\t\t\t#jesd204-cells = <2>;\n"
            "\t\t\tjesd204-top-device = <0>;\n"
            f"\t\t\tjesd204-link-ids = <{trx_link_ids_value}>;\n"
            f"\t\t\tjesd204-inputs = {trx_inputs_value};\n"
            "\t\t\tadi,rx-profile-rx-fir-num-fir-coefs = <48>;\n"
            "\t\t\tadi,rx-profile-rx-fir-coefs = /bits/ 16 <(-2) (23) (46) (-17) (-104) (10) (208) (23) (-370) (-97) (607) (240) (-942) (-489) (1407) (910) (-2065) (-1637) (3058) (2995) (-4912) (-6526) (9941) (30489) (30489) (9941) (-6526) (-4912) (2995) (3058) (-1637) (-2065) (910) (1407) (-489) (-942) (240) (607) (-97) (-370) (23) (208) (10) (-104) (-17) (46) (23) (-2)>;\n"
            "\t\t\tadi,rx-profile-rx-adc-profile = /bits/ 16 <182 142 173 90 1280 982 1335 96 1369 48 1012 18 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;\n"
            "\t\t\tadi,orx-profile-rx-fir-num-fir-coefs = <24>;\n"
            "\t\t\tadi,orx-profile-rx-fir-coefs = /bits/ 16 <(-10) (7) (-10) (-12) (6) (-12) (16) (-16) (1) (63) (-431) (17235) (-431) (63) (1) (-16) (16) (-12) (6) (-12) (-10) (7) (-10) (0)>;\n"
            "\t\t\tadi,orx-profile-orx-low-pass-adc-profile = /bits/ 16 <185 141 172 90 1280 942 1332 90 1368 46 1016 19 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;\n"
            "\t\t\tadi,orx-profile-orx-band-pass-adc-profile = /bits/ 16 <0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0>;\n"
            "\t\t\tadi,orx-profile-orx-merge-filter = /bits/ 16 <0 0 0 0 0 0 0 0 0 0 0 0>;\n"
            "\t\t\tadi,tx-profile-tx-fir-num-fir-coefs = <40>;\n"
            "\t\t\tadi,tx-profile-tx-fir-coefs = /bits/ 16 <(-14) (5) (-9) (6) (-4) (19) (-29) (27) (-30) (46) (-63) (77) (-103) (150) (-218) (337) (-599) (1266) (-2718) (19537) (-2718) (1266) (-599) (337) (-218) (150) (-103) (77) (-63) (46) (-30) (27) (-29) (19) (-4) (6) (-9) (5) (-14) (0)>;\n"
            "\t\t\tadi,tx-profile-loop-back-adc-profile = /bits/ 16 <206 132 168 90 1280 641 1307 53 1359 28 1039 30 48 48 37 210 0 0 0 0 53 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905>;\n"
            "\t\t};\n"
            "\t};",
            "\t&axi_adrv9009_core_rx {\n\t\tspibus-connected = <&trx0_adrv9009>;\n\t};",
            "\t&axi_adrv9009_core_rx_obs {\n"
            "\t\tclocks = <&trx0_adrv9009 1>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};",
            "\t&axi_adrv9009_core_tx {\n"
            "\t\tspibus-connected = <&trx0_adrv9009>;\n"
            "\t\tclocks = <&trx0_adrv9009 2>;\n"
            '\t\tclock-names = "sampl_clk";\n'
            "\t};",
        ]
        if rx_os_jesd_label:
            nodes.insert(
                2,
                f"\t&{rx_os_clkgen_label} {{\n"
                '\t\tcompatible = "adi,axi-clkgen-2.00.a";\n'
                "\t\t#clock-cells = <0>;\n"
                f'\t\tclock-output-names = "{rx_os_clkgen_label}";\n'
                '\t\tclock-names = "clkin1", "s_axi_aclk";\n'
                "\t};",
            )
            nodes.insert(
                3,
                f"\t&{rx_os_jesd_label} {{\n"
                '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
                f"\t\tclocks = <&zynqmp_clk 71>, <&{rx_os_clkgen_label}>, <&{rx_os_xcvr_label} 0>;\n"
                '\t\tclock-names = "s_axi_aclk", "device_clk", "lane_clk";\n'
                "\t\t#clock-cells = <0>;\n"
                "\t\tjesd204-device;\n"
                "\t\t#jesd204-cells = <2>;\n"
                "\t\tadi,octets-per-frame = <2>;\n"
                f"\t\tadi,frames-per-multiframe = <{rx_k}>;\n"
                f"\t\tjesd204-inputs = <&{rx_os_xcvr_label} 0 2>;\n"
                "\t};",
            )
        return nodes
