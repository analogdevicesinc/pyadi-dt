from typing import Dict
from adidt.dt import dt
import fdt
import math

from adidt.parts.clock_dt import clock_dt

class hmc7044_dt(dt, clock_dt):
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

        # Set input reference frequencies
        if "reference_frequencies" in clock:
            ref_freqs_prop_name = "adi,pll1-clkin-frequencies"
            ref_freqs_prop = node.get_property(ref_freqs_prop_name)
            if ref_freqs_prop is None:
                raise Exception(ref_freqs_prop_name + " property not in DT.")

            node.set_property(ref_freqs_prop_name, clock["reference_frequencies"])

            # Set same frequencies to dummy input clocks too
            used_clocks = self.get_used_clocks(node)
            i = 0
            for used_clock in used_clocks:
                compat_prop = used_clock.get_property("compatible")
                if compat_prop.value != "fixed-clock":
                    i += 1
                    continue

                used_clock.set_property("clock-frequency", clock["reference_frequencies"][i])
                i += 1

        # Set reference selection priorities
        if ("reference_selection_order" in clock):
            ref_order_val = 0
            priority = 0
            # MSB (Fourth priority input [1:0]) .... (First priority input [1:0]) LSB
            for ref_nr in clock["reference_selection_order"]:
                if (ref_nr > 4):
                    raise Exception("Refernce number:" + str(ref_nr) + " invalid.")
                ref_order_val |= (ref_nr << (priority * 2))
                priority += 1

            node.set_property("adi,pll1-ref-prio-ctrl", ref_order_val)

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
