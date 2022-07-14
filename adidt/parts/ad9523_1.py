import math
from typing import Dict

import fdt
import numpy as np
from adidt.parts.clock_dt import clock_dt


class ad9523_1_dt(clock_dt):
    """AD9523-1 Device tree map class."""

    compatible_id = "adi,ad9523-1"

    def set_dt_node_from_config(self, node: fdt.Node, config: Dict, append=False):
        """Set AD9523-1 node from JIF configuration

        Args:
            node (fdt.Node): Device tree parent node of AD9523-1
            config (Dict): Configuration struct generated from JIF
            append (boolean): Enable appending to subnode, if false the existing are removed
        """
        self.set_vcxo(node, config["vcxo"])

        # Set PLL frequency using one of the output clocks
        k1 = list(config["output_clocks"].keys())
        c = config["output_clocks"][k1[0]]
        p2f = c["divider"] * c["rate"]
        if math.trunc(p2f) != p2f:
            raise Exception("Floats not supported")
        self.handle_64bit("adi,pll2-m1-freq", node, int(p2f))

        # Output divider sets
        existing_names = self.get_prop_across_nodes(node, "adi,extended-name")
        regs = self.get_prop_across_nodes(node, "reg")
        names = config["output_clocks"].keys()
        for name in names:
            if name in existing_names:
                sn = self.get_node_by_prop(node, "adi,extended-name", name)
                self.update_existing_clock_node(sn, config["output_clocks"][name])
                print(f"Found: {name}")
            else:
                reg = int(np.max(regs) + 1)
                regs.append(reg)
                self.set_clock_node(node, config["output_clocks"][name], name, reg)
