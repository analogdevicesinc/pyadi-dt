from typing import Dict
from adidt.dt import dt
import fdt
import math


class hmc7044_dt(dt):
    """HMC7044 Device tree map class."""

    def set_clock_node(self, parent, clk, name, reg):
        node = fdt.Node(f"channel@{reg}")

        node.append(fdt.PropWords("reg", reg))
        node.append(fdt.PropStrings("adi,extended-name", str(name)))
        node.append(fdt.PropWords("adi,divider", clk["divider"]))
        node.append(fdt.PropWords("adi,driver-mode", 2))

        parent.append(node)

    def set_dt_node_from_config(self, node: fdt.Node, config: Dict, append=False):
        """Set HMC7044 node from JIF configuration

        Args:
            node (fdt.Node): Device tree parent node of hmc7044
            config (Dict): Configuration struct generated from JIF
            append (boolean): Enable appending to subnode, if false the existing are removed
        """
        clock = config["clock"]
        # Set VCXO
        vcxo = config["vcxo"]
        node.set_property("adi,vcxo-frequency", vcxo)
        # Set PLL frequency using one of the output clocks
        k1 = list(clock["output_clocks"].keys())
        c = clock["output_clocks"][k1[0]]
        p2f = c["divider"] * c["rate"]
        if math.trunc(p2f) != p2f:
            raise Exception("Floats not supported")
        node.set_property("adi,pll2-output-frequency", int(p2f))
        if not append:
            # Clear existing nodes
            nn = [sn.name for sn in node.nodes]
            for name in nn:
                node.remove_subnode(name)
        for reg, clockout in enumerate(clock["output_clocks"]):
            # Add node
            self.set_clock_node(node, clock["output_clocks"][clockout], clockout, reg)