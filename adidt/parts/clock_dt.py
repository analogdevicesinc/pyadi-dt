from adidt import parts
from typing import Dict
import fdt
import math


class clock_dt:
    def handle_64bit(self, prop, node, num):
        if num > 2 ** 31:
            h = hex(int(num))
            # Inflate
            h = "0x" + "0" * (16 - len(h) + 2) + h[2:]
            a = [int(h[:-8], 0), int("0x" + h[-8:], 0)]
            node.set_property(prop, a)
        else:
            node.set_property(prop, int(num))

    def set_clock_node(self, parent, clk, name, reg):
        node = fdt.Node(f"channel@{reg}")

        node.append(fdt.PropWords("reg", reg))
        node.append(fdt.PropStrings("adi,extended-name", str(name)))
        node.append(fdt.PropWords("adi,driver-mode", 2))
        node.append(fdt.PropWords("adi,divider-phase", 1))
        node.append(fdt.PropWords("adi,channel-divider", clk["divider"]))

        parent.append(node)

    def setter(self, node, prop_name, value):
        existing_props = [prop.name for prop in node.props]
        if prop_name not in existing_props:
            node.append(fdt.PropWords(prop_name, value))
        else:
            node.set_property(prop_name, value)

    def update_existing_clock_node(self, node, clk):
        self.setter(node, "adi,channel-divider", clk["divider"])
        props_to_set = ["adi,driver-mode", "adi,divider-phase"]
        defaults_to_set = [2, 1]
        for pts, val in zip(props_to_set, defaults_to_set):
            self.setter(node, pts, val)

    def set_vcxo(self, node, vcxo):
        if math.trunc(vcxo) != vcxo:
            raise Exception("Floats not supported")
        node.set_property("adi,vcxo-frequency", int(vcxo))

    def get_prop_across_nodes(self, node, prop):
        return [sn.get_property(prop).value for sn in node.nodes]

    def get_node_by_prop(self, parent, prop, value):
        for sn in parent.nodes:
            for prop in sn.props:
                if prop.value == value:
                    return sn
        return False

    """ Get nodes that are pointed at by the phandles in "clocks" CCF property

    Args:
        node (fdt.Node): Device tree node of a clock

    Returns:
        A list containing all nodes refered to in the "clocks" phandle array
    """
    def get_used_clocks(self, node):
        used_clocks = []
        clocks_prop = node.get_property("clocks")
        if clocks_prop is not None:
            clocks_val = list(clocks_prop)

            # first value in "clocks" property is a phandle
            # next phandle is located after "#clock-cells"+1 positions
            for i in range(0, len(clocks_val)):
                clock_phandle = clocks_val[i]
                phandle_props = self._dt.search("phandle")

                clock = None
                for phandle_prop in phandle_props:
                    if phandle_prop[0] == clock_phandle:
                        clock = phandle_prop.parent

                if clock is None:
                    continue

                clock_cells = clock.get_property("#clock-cells")
                if clock_cells is None:
                    continue

                used_clocks.append(clock)
                i += clock_cells[0] + 1

        return used_clocks
