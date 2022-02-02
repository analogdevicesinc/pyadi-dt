from typing import Dict
from adidt.dt import dt
import fdt
import math


class ad9545_dt(dt):
    """AD9545 Device tree map class."""

    pll_clock_id = 1
    out_clock_id = 0

    def set_clock_node(self, parent, clk, name, reg):
        node = fdt.Node(f"output-clk@{reg}")

        node.append(fdt.PropWords("reg", reg))
        parent.append(node)

    def pll_set_rate(self, pll_nr: int, rate: int, node: fdt.Node):
        #rate change for PLLs is trickier, it is found in the assigned-clocks/assigned-clock-rates
        assigned_clocks_prop = node.get_property("assigned-clocks")
        assigned_clocks = []

        # find pll clock position in the assigned-clock-rates dt list
        clock_pos = -1
        for i in range(0, int(len(assigned_clocks_prop) / 3)):
            clock_type = assigned_clocks_prop[3 * i + 1]
            clock_address = assigned_clocks_prop[3 * i + 2]

            if clock_address == pll_nr and clock_type == self.pll_clock_id:
                clock_pos = i

        if clock_pos == -1:
            raise Exception("AD9545: missing PLL" + str(pll_nr) + " in assigned-clocks prop.")

        assigned_clock_rates_prop = node.get_property("assigned-clock-rates")
        assigned_clock_rates = list(assigned_clock_rates_prop)
        assigned_clock_rates[clock_pos] = rate

        assigned_clock_rates_prop.clear()
        for assigned_rate in assigned_clock_rates:
            assigned_clock_rates_prop.append(int(assigned_rate))

    def output_set_rate(self, output_nr: int, rate: int, node: fdt.Node):
        #rate change for PLLs is trickier, it is found in the assigned-clocks/assigned-clock-rates
        assigned_clocks_prop = node.get_property("assigned-clocks")
        assigned_clocks = []

        # find pll clock position in the assigned-clock-rates dt list
        clock_pos = -1
        for i in range(0, int(len(assigned_clocks_prop) / 3)):
            clock_type = assigned_clocks_prop[3 * i + 1]
            clock_address = assigned_clocks_prop[3 * i + 2]

            if clock_address == output_nr and clock_type == self.out_clock_id:
                clock_pos = i

        if clock_pos == -1:
            raise Exception("AD9545: missing output" + str(output_nr) + " in assigned-clocks prop.")

        assigned_clock_rates_prop = node.get_property("assigned-clock-rates")
        assigned_clock_rates = list(assigned_clock_rates_prop)
        assigned_clock_rates[clock_pos] = rate

        assigned_clock_rates_prop.clear()
        for assigned_rate in assigned_clock_rates:
            assigned_clock_rates_prop.append(int(assigned_rate))

    def set_source_priorities_from_config(self, node: fdt.Node, config: Dict):
        for i in range(0, 2):
            pll_name = "PLL" + str(i)
            if pll_name not in config:
                continue

            pll_node = node.get_subnode("pll-clk@" + str(i))
            if pll_node is None:
                continue

            for j in range(0, 6):
                pll_profile_node = pll_node.get_subnode("profile@" + str(j))
                if pll_profile_node is None:
                    continue;

                adi_pll_source_nr = list(pll_profile_node.get_property("adi,pll-source"))[0]

                if ("priority_source_" + str(adi_pll_source_nr)) in config[pll_name]:
                    new_priority = config[pll_name]["priority_source_" + str(adi_pll_source_nr)]
                    pll_profile_node.set_property("adi,profile-priority", new_priority)

    def set_dt_node_from_config(self, node: fdt.Node, config: Dict, append=False):
        """Set AD9545 node from JIF configuration

        Args:
            node (fdt.Node): Device tree parent node of ad9545
            config (Dict): Configuration struct generated from JIF
        """

        #set input dividers
        for i in range(0, 4):
            if "r" + str(i) not in config:
                continue

            r_div = int(config["r" + str(i)])

            if r_div != 0:
                ref_node = node.get_subnode("ref-input-clk@" + str(i))
                if ref_node is None:
                    raise Exception("AD9545: missing node: ref-input-clk@" + str(i))

                ref_node.set_property("adi,r-divider-ratio", r_div)

        #set PLL rates in the DT
        PLL_rates = [0, 0]
        for i in range(0, 2):
            if "PLL" + str(i) not in config:
                continue

            pll_dict = config["PLL" + str(i)]

            if "rate_hz" in pll_dict:
                self.pll_set_rate(i, pll_dict["rate_hz"], node)
                PLL_rates[i] = pll_dict["rate_hz"]

        #set PLL sources priorities
        self.set_source_priorities_from_config(node, config)

        # Add/remove hitless mode from DT per PLL
        for i in range(0, 2):
            if "PLL" + str(i) not in config:
                continue

            pll_dict = config["PLL" + str(i)]
            hitless_enable = ("hitless" in pll_dict)
            pll_node = node.get_subnode("pll-clk@" + str(i))

            if hitless_enable:
                hitless_dict = pll_dict["hitless"]
                fb_source_nr = hitless_dict["fb_source"]
                fb_source_rate = hitless_dict["fb_source_rate"]

                pll_node.set_property(
                    "adi,pll-internal-zero-delay-feedback",
                    fb_source_nr,
                )

                pll_node.set_property(
                    "adi,pll-internal-zero-delay-feedback-hz",
                    fb_source_rate,
                )

                # set slew rate limit to 4 ms / s during hitless phase acq
                pll_node.set_property(
                    "adi,pll-slew-rate-limit-ps",
                    4000000000,
                )
            else:
                try:
                    pll_node.remove_property(
                        "adi,pll-internal-zero-delay-feedback"
                    )

                    pll_node.remove_property(
                        "adi,pll-internal-zero-delay-feedback-hz"
                    )

                    # set slew rate limit to default value during PBO mode
                    pll_node.set_property(
                        "adi,pll-slew-rate-limit-ps",
                        100000000,
                    )
                except ValueError:
                    pass

        #set output rates
        for i in range(0, 10):
            if "q" + str(i) not in config:
                continue

            q_div = int(config["q" + str(i)])

            if q_div == 0:
                continue

            if i > 5:
                output_rate = int(PLL_rates[1] / q_div)
            else:
                output_rate = int(PLL_rates[0] / q_div)

            self.output_set_rate(i, output_rate, node)
