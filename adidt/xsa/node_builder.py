# adidt/xsa/node_builder.py
import os
import warnings
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .topology import XsaTopology, Jesd204Instance, ClkgenInstance


class NodeBuilder:
    """Builds ADI DTS node strings from XsaTopology + pyadi-jif JSON config."""

    def build(self, topology: XsaTopology, cfg: dict[str, Any]) -> dict[str, list[str]]:
        """Render ADI DTS nodes.

        Returns:
            Dict with keys "jesd204_rx", "jesd204_tx", "converters".
        """
        env = self._make_jinja_env()
        clock_map = self._build_clock_map(topology)
        result: dict[str, list[str]] = {"jesd204_rx": [], "jesd204_tx": [], "converters": []}

        for inst in topology.jesd204_rx:
            clkgen_label, hmc_ch = self._resolve_clock(inst, clock_map, cfg, "rx")
            result["jesd204_rx"].append(
                self._render_jesd(env, inst, cfg.get("jesd", {}).get("rx", {}), clkgen_label, hmc_ch)
            )

        for inst in topology.jesd204_tx:
            clkgen_label, hmc_ch = self._resolve_clock(inst, clock_map, cfg, "tx")
            result["jesd204_tx"].append(
                self._render_jesd(env, inst, cfg.get("jesd", {}).get("tx", {}), clkgen_label, hmc_ch)
            )

        for conv in topology.converters:
            result["converters"].append(self._render_converter(env, conv, result))

        return result

    def _make_jinja_env(self) -> Environment:
        loc = os.path.join(os.path.dirname(__file__), "..", "templates", "xsa")
        return Environment(loader=FileSystemLoader(loc))

    def _build_clock_map(self, topology: XsaTopology) -> dict[str, ClkgenInstance]:
        return {net: cg for cg in topology.clkgens for net in cg.output_clks}

    def _resolve_clock(
        self,
        inst: Jesd204Instance,
        clock_map: dict[str, ClkgenInstance],
        cfg: dict[str, Any],
        direction: str,
    ) -> tuple[str, int]:
        clkgen = clock_map.get(inst.link_clk)
        if clkgen is None:
            warnings.warn(
                f"unresolved clock net '{inst.link_clk}' for {inst.name}; "
                "using literal net name as clock label",
                UserWarning,
                stacklevel=3,
            )
            return inst.link_clk, 0
        return (
            clkgen.name.replace("-", "_"),
            cfg.get("clock", {}).get(f"hmc7044_{direction}_channel", 0),
        )

    def _render_jesd(
        self,
        env: Environment,
        inst: Jesd204Instance,
        jesd_params: dict[str, Any],
        clkgen_label: str,
        hmc_channel: int,
    ) -> str:
        return env.get_template("jesd204_fsm.tmpl").render(
            instance=inst, jesd=jesd_params,
            clkgen_label=clkgen_label, hmc_channel=hmc_channel,
        )

    def _render_converter(self, env: Environment, conv, nodes: dict[str, list[str]]) -> str:
        try:
            tmpl = env.get_template(f"{conv.ip_type}.tmpl")
        except Exception:
            return f"\t/* {conv.name}: no template for {conv.ip_type} */"
        rx_label = nodes["jesd204_rx"][0].split(":")[0].strip() if nodes["jesd204_rx"] else "jesd_rx"
        tx_label = nodes["jesd204_tx"][0].split(":")[0].strip() if nodes["jesd204_tx"] else "jesd_tx"
        return tmpl.render(
            instance=conv, rx_jesd_label=rx_label, tx_jesd_label=tx_label,
            spi_label="spi0", spi_cs=conv.spi_cs if conv.spi_cs is not None else 0,
        )
