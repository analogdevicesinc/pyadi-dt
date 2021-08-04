from typing import Dict
from adidt.dt import dt
import fdt
import math


class ad9081_config:
    fduc_enabled_channels = [0, 1, 2, 3]
    cduc_enabled_channels = [0, 1, 2, 3]
    fduc_cduc_crossbar = [0, 1, 2, 3]
    fduc_interpolation = 6
    cduc_interpolation = 8


def get_phandles(root):
    all_nodes = []
    phandle_value = 0
    no_phandle_nodes = []
    phandles = []

    node = root
    all_nodes += root.nodes
    while all_nodes:
        props = (node.get_property("phandle"), node.get_property("linux,phandle"))
        value = None
        for i, p in enumerate(props):
            if isinstance(p, fdt.PropWords) and isinstance(p.value, int):
                value = None if i == 1 and p.value != value else p.value
                print(p.value)
        if value:
            phandles.append(value)
        if value is None:
            no_phandle_nodes.append(node)
        elif phandle_value < value:
            phandle_value = value
        # ...
        node = all_nodes.pop()
        all_nodes += node.nodes

    # if phandle_value > 0:
    #     phandle_value += 1

    # for node in no_phandle_nodes:
    #     node.set_property('linux,phandle', phandle_value)
    #     node.set_property('phandle', phandle_value)
    #     phandle_value += 1
    return phandles


class ad9081_dt(dt):
    """AD9081 Device tree map class."""

    def new_phandle(self):
        i = 1
        while True:
            if i in self.phandles:
                i += 1
            else:
                self.phandles.append(i)
                return i

    def set_clock_node(self, parent, clk, name, reg):
        node = fdt.Node(f"channel@{reg}")

        node.append(fdt.PropWords("reg", reg))
        node.append(fdt.PropStrings("adi,extended-name", str(name)))
        node.append(fdt.PropWords("adi,divider", clk["divider"]))
        node.append(fdt.PropWords("adi,driver-mode", 2))

        parent.append(node)

    def handle_64bit(self, prop, node, num):
        if num > 2 ** 31:
            h = hex(int(num))
            a = [int(h[:-8], 0), int("0x" + h[-8:], 0)]
            node.set_property(prop, a)
        else:
            node.set_property(prop, int(num))

    def add_cduc_channels_nodes(self, parent_node, model):

        tnode = fdt.Node("adi,main-data-paths")

        tnode.set_property("#address-cells", 1)
        tnode.set_property("#size-cells", 0)

        tnode.set_property("adi,interpolation", model.cduc_interpolation)

        cp: fdt.Node = parent_node.get_subnode("adi,channelizer-paths")

        index = 0
        for cduc in model.cduc_enabled_channels:
            node = fdt.Node(f"ad9081_dac{cduc}: dac@{cduc}")
            node.set_property("reg", 0)
            # FIXME: Check source FDUC valid
            source = model.fduc_cduc_crossbar[index]
            n: fdt.Node = cp.get_subnode(
                f"ad9081_tx_fddc_chan{source}: channel@{source}"
            )
            ref = n.get_property("phandle")
            node.set_property("adi,crossbar-select", ref[0])
            index += 1
            tnode.append(node)

        parent_node.append(tnode)

    def add_fduc_channels_nodes(self, parent_node: fdt.Node, model):

        tnode = fdt.Node("adi,channelizer-paths")

        tnode.set_property("#address-cells", 1)
        tnode.set_property("#size-cells", 0)

        tnode.set_property("adi,interpolation", model.fduc_interpolation)

        for fduc in model.fduc_enabled_channels:
            node = fdt.Node(f"ad9081_tx_fddc_chan{fduc}: channel@{fduc}")
            node.set_property("reg", fduc)
            node.set_property("adi,gain", 2048)
            self.handle_64bit("adi,nco-frequency-shift-hz", node, 0)
            node.set_property("phandle", self.new_phandle())

            tnode.append(node)

        parent_node.append(tnode)

    def update_datapath(self, parent_node, node, model):
        if not node:
            node = fdt.Node("adi,tx-dacs")
        self.handle_64bit("adi,dac-frequency-hz", node, int(12e9))

        node.remove_subnode("adi,main-data-paths")
        node.remove_subnode("adi,channelizer-paths")

        # Configure from JESD->DAC
        self.add_fduc_channels_nodes(node, model)
        self.add_cduc_channels_nodes(node, model)

        # parent_node.add_item(node)

    def update_dt_node_from_config(
        self, node: fdt.Node, config: Dict, d: fdt.FDT, append=False
    ):
        """Set AD9081 node from JIF configuration

        Args:
            node (fdt.Node): Device tree parent node of AD9081
            config (Dict): Configuration struct generated from JIF
            append (boolean): Enable appending to subnode, if false the existing are removed
        """

        self.phandles = get_phandles(d.root)

        model = ad9081_config()

        node.set_property("#address-cells", 1)
        node.set_property("#size-cells", 0)

        node.set_property("reg", 0)

        node.set_property("spi-max-frequency", 5000000)

        # clocks = <&hmc7044 2>; # Should be set from phandle of hmc7044 node
        node.set_property("clock-names", "dev_clk")

        node.set_property("clock-output-names", ["rx_sampl_clk", "tx_sampl_clk"])

        if not node.exist_property("jesd204-device"):
            node.append(fdt.Property("jesd204-device"))

        # Set as top device
        node.set_property("jesd204-top-device", 0)

        # jesd204-link-ids = <FRAMER_LINK0_RX DEFRAMER_LINK0_TX>;
        # jesd204-inputs =
        #         <&axi_ad9081_core_rx 0 FRAMER_LINK0_RX>,
        #         <&axi_ad9081_core_tx 0 DEFRAMER_LINK0_TX>;
        # node.set_property("jesd204-link-ids", [FRAMER_LINK0_RX, DEFRAMER_LINK0_TX])
        # node.append(fdt.PropStrings("jesd204-link-ids",'FRAMER_LINK0_RX','DEFRAMER_LINK0_TX'))

        self.update_datapath(node, node.get_subnode("adi,tx-dacs"), model)

    def set_dt_node_from_config(self, node: fdt.Node, config: Dict, append=False):
        """Set AD9081 node from JIF configuration

        Args:
            node (fdt.Node): Device tree parent node of AD9081
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
