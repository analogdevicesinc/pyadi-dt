from typing import Dict
from adidt.dt import dt
import fdt
import math

from adidt.parts.clock_dt import clock_dt

class hmc7044_dt(dt, clock_dt):
    """HMC7044 Device tree map class."""

    pulse_gen_modes = {
        "GEN_LEVEL_SENSITIVE" : 0,
        "GEN_1_PULSE" : 1,
        "GEN_2_PULSE" : 2,
        "GEN_4_PULSE" : 3,
        "GEN_8_PULSE" : 4,
        "GEN_16_PULSE" : 5,
        "GEN_CONT_PULSE" : 7,
    }

    driver_modes = {
        "CML" : 0,
        "LVPECL" : 1,
        "LVDS" : 2,
        "CMOS" : 3,
    }

    driver_impedances = {
        "DISABLE" : 0,
        "100_OHM" : 1,
        "50_OHM" : 3,
    }

    output_mux_modes = {
        "CH_DIV" : 0,
        "ANALOG_DELAY" : 1,
        "GROUP_PAIR" : 3,
        "VCO_CLOCK" : 4,
    }

    cmos_outputs_reg_field_map = {
        0 : {"P" : 1, "N" : 0},
        1 : {"P" : 0, "N" : 1},
        2 : {"P" : 0, "N" : 1},
        3 : {"P" : 1, "N" : 0},
        4 : {"P" : 0, "N" : 1},
        5 : {"P" : 1, "N" : 0},
        6 : {"P" : 1, "N" : 0},
        7 : {"P" : 0, "N" : 1},
        8 : {"P" : 0, "N" : 1},
        9 : {"P" : 1, "N" : 0},
        10 : {"P" : 1, "N" : 0},
        11 : {"P" : 0, "N" : 1},
        12 : {"P" : 0, "N" : 1},
        13 : {"P" : 1, "N" : 0},
    }

    def set_clock_node(self, parent, clk, name, reg):
        node = fdt.Node(f"channel@{reg}")

        node.append(fdt.PropWords("reg", reg))
        node.append(fdt.PropStrings("adi,extended-name", str(name)))
        node.append(fdt.PropWords("adi,divider", clk["divider"]))

        driver_mode = self.driver_modes[clk["driver-mode"]]
        node.append(fdt.PropWords("adi,driver-mode", driver_mode))

        if ("high-performance-mode-disable" in clk):
            node.append(fdt.Property("adi,high-performance-mode-disable"))

        if ("startup-mode-dynamic-enable" in clk):
            node.append(fdt.Property("adi,startup-mode-dynamic-enable"))

            if ("dynamic-driver-enable" in clk):
                node.append(fdt.Property("adi,dynamic-driver-enable"))

            if ("force-mute-enable" in clk):
                node.append(fdt.Property("adi,force-mute-enable"))

        if ("output-mux-mode" in clk):
            mux_mode = self.output_mux_modes[clk["output-mux-mode"]]
            node.append(fdt.PropWords("adi,output-mux-mode", mux_mode))

        if ("driver-impedance-mode" in clk):
            impedance_mode = self.driver_impedances[clk["driver-impedance-mode"]]
            node.append(fdt.PropWords("adi,driver-impedance-mode", impedance_mode))

        if ("fine-delay" in clk):
            node.append(fdt.PropWords("adi,fine-analog-delay", clk["fine-delay"]))

        if ("coarse-delay" in clk):
            node.append(fdt.PropWords("adi,coarse-digital-delay", clk["coarse-delay"]))

        # in CMOS mode, the impedance property describes the output status
        if ("CMOS" in clk):
            prop_val = (clk["CMOS"]["P"] << self.cmos_outputs_reg_field_map[reg]["P"])
            propval = prop_val | (clk["CMOS"]["N"] << self.cmos_outputs_reg_field_map[reg]["N"])
            node.append(fdt.PropWords("adi,driver-impedance-mode", prop_val))

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
