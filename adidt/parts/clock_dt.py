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
