from typing import Dict
from adidt.dt import dt
import fdt
import math


class jesd:
    N = 1
    L = 1
    S = 1
    NP = 1
    HD = 1
    CS = 1
    DL = 1
    M = 1
    F = 1
    K = 1
    subclass = 1
    version = 1
    mode = 11
    complex_channels = True
    lane_map = [2, 0, 7, 7, 7, 7, 3, 1]


class ad9081_config:
    # CONSTANTS
    FRAMER_LINK0_RX = 2
    FRAMER_LINK1_RX = 3
    DEFRAMER_LINK0_TX = 0
    DEFRAMER_LINK1_TX = 1

    # TX
    tx_jesd_config = jesd()
    dac_rate = 12e9
    fduc_enabled_channels = [0, 1, 2, 3]
    cduc_enabled_channels = [0, 1, 2, 3]
    fduc_cduc_crossbar = [0, 1, 2, 3]
    fduc_interpolation = 6
    cduc_interpolation = 8
    # RX
    rx_jesd_config = jesd()
    adc_rate = 4e9
    fddc_enabled_channels = [0, 1, 2, 3]
    cddc_enabled_channels = [0, 1, 2, 3]
    fddc_cddc_crossbar = [0, 1, 2, 3]
    fddc_decimation = 6
    cddc_decimation = 8
    cddc_freq_shift = [0, 0, 0, 0]
    fddc_freq_shift = [0, 0, 0, 0]
    cddc_nco_mode = [0, 0, 0, 0]
    fddc_nco_mode = [0, 0, 0, 0]
    fddc_gain = [0, 0, 0, 0]


def get_phandles(root):
    all_nodes = []
    phandles = []

    node = root
    all_nodes += root.nodes
    while all_nodes:
        props = (node.get_property("phandle"), node.get_property("linux,phandle"))
        value = None
        for i, p in enumerate(props):
            if isinstance(p, fdt.PropWords) and isinstance(p.value, int):
                value = None if i == 1 and p.value != value else p.value
        if value:
            phandles.append(value)
        node = all_nodes.pop()
        all_nodes += node.nodes

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

    def handle_64bit(self, prop, node, num):
        if num > 2 ** 31:
            h = hex(int(num))
            # Inflate
            h = "0x" + "0" * (16 - len(h) + 2) + h[2:]
            a = [int(h[:-8], 0), int("0x" + h[-8:], 0)]
            node.set_property(prop, a)
        else:
            node.set_property(prop, int(num))

    def add_jesd_link(self, data_path_node, model, tx_0_rx_1):
        ttnode = fdt.Node("adi,jesd-links")

        ttnode.set_property("#address-cells", 1)
        ttnode.set_property("#size-cells", 0)

        data_path_node.append(ttnode)

        jesd = model.rx_jesd_config if tx_0_rx_1 else model.tx_jesd_config
        tnode = (
            fdt.Node("ad9081_rx_jesd_l0: link@0")
            if tx_0_rx_1
            else fdt.Node("ad9081_tx_jesd_l0: link@0")
        )

        if not tx_0_rx_1:
            tnode.set_property("#address-cells", 1)
            tnode.set_property("#size-cells", 0)

        tnode.set_property("reg", 0)
        cp: fdt.Node = data_path_node.get_subnode("adi,channelizer-paths")

        if tx_0_rx_1:
            phandles = []
            for fddc in model.fddc_enabled_channels:
                n: fdt.Node = cp.get_subnode(
                    f"ad9081_rx_fddc_chan{fddc}: channel@{fddc}"
                )
                ref = n.get_property("phandle")
                phandles.append(ref[0])
                if jesd.complex_channels:
                    phandles.append(0)
                    phandles.append(ref[0])
                    phandles.append(1)

            tnode.set_property("adi,converter-select", phandles)

        lane_map = 0
        for index, fdc in enumerate(reversed(jesd.lane_map)):
            lane_map += fdc << index * 2 * 4

        self.handle_64bit("adi,logical-lane-mapping", tnode, int(lane_map))

        tnode.set_property("adi,link-mode", jesd.mode)
        tnode.set_property("adi,subclass", jesd.subclass)
        tnode.set_property("adi,version", jesd.version)

        tnode.set_property("adi,dual-link", jesd.DL)
        tnode.set_property("adi,converters-per-device", jesd.M)
        tnode.set_property("adi,octets-per-frame", jesd.F)
        tnode.set_property("adi,frames-per-multiframe", jesd.K)
        tnode.set_property("adi,converter-resolution", jesd.N)
        tnode.set_property("adi,bits-per-sample", jesd.NP)
        tnode.set_property("adi,control-bits-per-sample", jesd.CS)
        tnode.set_property("adi,lanes-per-device", jesd.L)
        tnode.set_property("adi,samples-per-converter-per-frame", jesd.S)
        tnode.set_property("adi,high-density", jesd.HD)

        ttnode.append(tnode)

    def add_cddc_channels_nodes(self, parent_node, model):

        tnode = fdt.Node("adi,main-data-paths")

        tnode.set_property("#address-cells", 1)
        tnode.set_property("#size-cells", 0)

        for index, cddc in enumerate(model.cddc_enabled_channels):
            node = fdt.Node(f"adc@{cddc}")
            node.set_property("reg", index)
            node.set_property("adi,decimation", model.cddc_decimation)
            self.handle_64bit(
                "adi,nco-frequency-shift-hz", node, int(model.cddc_freq_shift[index])
            )
            node.set_property("adi,nco-mode", model.cddc_nco_mode[index])
            tnode.append(node)

        parent_node.append(tnode)

    def add_fddc_channels_nodes(self, parent_node, model):

        tnode = fdt.Node("adi,channelizer-paths")

        tnode.set_property("#address-cells", 1)
        tnode.set_property("#size-cells", 0)

        for index, fddc in enumerate(model.fddc_enabled_channels):
            node = fdt.Node(f"ad9081_rx_fddc_chan{fddc}: channel@{fddc}")
            node.set_property("reg", index)
            node.set_property("adi,decimation", model.cddc_decimation)
            node.set_property("adi,gain", model.fddc_gain[index])
            self.handle_64bit(
                "adi,nco-frequency-shift-hz", node, int(model.cddc_freq_shift[index])
            )
            node.set_property("phandle", self.new_phandle())

            tnode.append(node)

        parent_node.append(tnode)

    def add_cduc_channels_nodes(self, parent_node, model):

        tnode = fdt.Node("adi,main-data-paths")

        tnode.set_property("#address-cells", 1)
        tnode.set_property("#size-cells", 0)

        tnode.set_property("adi,interpolation", model.cduc_interpolation)

        cp: fdt.Node = parent_node.get_subnode("adi,channelizer-paths")

        for index, cduc in enumerate(model.cduc_enabled_channels):
            node = fdt.Node(f"ad9081_dac{cduc}: dac@{cduc}")
            node.set_property("reg", index)
            # FIXME: Check source FDUC valid
            source = model.fduc_cduc_crossbar[index]
            n: fdt.Node = cp.get_subnode(
                f"ad9081_tx_fddc_chan{source}: channel@{source}"
            )
            ref = n.get_property("phandle")
            node.set_property("adi,crossbar-select", ref[0])
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

    def update_tx_datapath(self, node, model):
        if not node:
            node = fdt.Node("adi,tx-dacs")
        self.handle_64bit("adi,dac-frequency-hz", node, int(model.dac_rate))

        node.remove_subnode("adi,main-data-paths")
        node.remove_subnode("adi,channelizer-paths")
        node.remove_subnode("adi,jesd-links")

        # Configure from JESD->DAC
        self.add_fduc_channels_nodes(node, model)
        self.add_cduc_channels_nodes(node, model)
        self.add_jesd_link(node, model, False)

    def update_rx_datapath(self, node, model):
        if not node:
            node = fdt.Node("adi,rx-adcs")
        self.handle_64bit("adi,adc-frequency-hz", node, int(model.adc_rate))

        node.remove_subnode("adi,main-data-paths")
        node.remove_subnode("adi,channelizer-paths")
        node.remove_subnode("adi,jesd-links")

        # Configure from ADC->JESD
        self.add_fddc_channels_nodes(node, model)
        self.add_cddc_channels_nodes(node, model)
        self.add_jesd_link(node, model, True)

    def update_dt_node_from_config(
        self, node: fdt.Node, clock_node: fdt.Node, config: Dict
    ):
        """Set AD9081 node from JIF configuration

        Args:
            node (fdt.Node): Device tree parent node of AD9081
            clock_node (fdt.Node): Device tree parent node of clock chip
            config (Dict): Configuration struct generated from JIF
        """

        self.phandles = get_phandles(self._dt.root)

        model = ad9081_config()

        node.set_property("#address-cells", 1)
        node.set_property("#size-cells", 0)

        node.set_property("reg", 0)

        node.set_property("spi-max-frequency", 5000000)

        p = clock_node.get_property("phandle")
        node.set_property("clocks", [p.value, 2])

        node.set_property("clock-names", "dev_clk")

        node.set_property("clock-output-names", ["rx_sampl_clk", "tx_sampl_clk"])

        if not node.exist_property("jesd204-device"):
            node.append(fdt.Property("jesd204-device"))

        node.set_property("#jesd204-cells", 2)

        # Set as top device
        node.set_property("jesd204-top-device", 0)

        node.set_property(
            "jesd204-link-ids", [model.FRAMER_LINK0_RX, model.DEFRAMER_LINK0_TX]
        )

        n = self.get_node_by_compatible("adi,axi-ad9081-rx")
        p_rx = n[0].get_property("phandle")
        n = self.get_node_by_compatible("adi,axi-ad9081-tx")
        p_tx = n[0].get_property("phandle")
        node.set_property(
            "jesd204-inputs",
            [
                p_rx.value,
                0,
                model.FRAMER_LINK0_RX,
                p_tx.value,
                0,
                model.DEFRAMER_LINK0_TX,
            ],
        )

        # Add data paths and JTRX links
        self.update_tx_datapath(node.get_subnode("adi,tx-dacs"), model)
        self.update_rx_datapath(node.get_subnode("adi,rx-adcs"), model)
