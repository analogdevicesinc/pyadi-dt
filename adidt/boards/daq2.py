from jinja2 import Environment, FileSystemLoader
import os


class layout:
    includes = [""]

    template_filename = None
    output_filename = None

    def gen_dt(self, **kwargs):

        if not self.template_filename:
            raise Exception("No template file specified")

        if not self.output_filename:
            raise Exception("No output file specified")

        # Import template
        loc = os.path.dirname(__file__)
        loc = os.path.join(loc, "..", "templates")
        file_loader = FileSystemLoader(loc)
        env = Environment(loader=file_loader)

        loc = os.path.join(self.template_filename)
        template = env.get_template(loc)
        # output = template.render(clock=clock, adc=adc, dac=dac)
        output = template.render(**kwargs)

        with open(self.output_filename, "w") as f:
            f.write(output)


    def map_jesd_subclass(self, name):
        modes = ["jesd204a", "jesd204b", "jesd204c"]
        if name not in modes:
            raise Exception("JESD Subclass {} not supported".format(name))
        return modes.index(name)


class daq2(layout):

    clock = "ad9523_1"

    adc = "ad9680"
    dac = "ad9144"

    template_filename = "daq2.tmpl"
    output_filename = "daq2.dts"

    def make_ints(self, cfg, keys):
        for key in keys:
            if cfg[key].is_integer():
                cfg[key] = int(cfg[key])
        return cfg

    def map_jesd_structs(self, cfg):
        adc = cfg["converter_AD9680"]
        adc["jesd"] = cfg["jesd_AD9680"]
        adc["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
            adc["jesd"]["jesd_class"]
        )
        dac = cfg["converter_AD9144"]
        dac["jesd"] = cfg["jesd_AD9144"]
        dac["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
            dac["jesd"]["jesd_class"]
        )

        adc["jesd"] = self.make_ints(adc["jesd"],['converter_clock','sample_clock'])
        dac["jesd"] = self.make_ints(dac["jesd"],['converter_clock','sample_clock'])

        return adc, dac

    def map_clocks_to_board_layout(self, cfg):

        # Fix ups
        for key in ['vco','vcxo']:
            if cfg['clock'][key].is_integer():
                cfg['clock'][key] = int(cfg['clock'][key])

        map = {}
        clk = cfg["clock"]["output_clocks"]

        # AD9680 side
        map["ADC_CLK"] = {
            "source_port": 13,
            "divider": clk["AD9680_ref_clk"]["divider"],
        }
        map["ADC_CLK_FMC"] = {
            "source_port": 4,
            "divider": clk["AD9680_fpga_ref_clk"]["divider"],
        }
        map["ADC_SYSREF"] = {
            "source_port": 5,
            "divider": clk["AD9680_sysref"]["divider"],
        }
        map["CLKD_ADC_SYSREF"] = {
            "source_port": 6,
            "divider": clk["AD9680_sysref"]["divider"],
        }

        # AD9144 side
        map["DAC_CLK"] = {"source_port": 1, "divider": clk["AD9144_ref_clk"]["divider"]}
        map["FMC_DAC_REF_CLK"] = {
            "source_port": 9,
            "divider": clk["AD9144_fpga_ref_clk"]["divider"],
        }
        map["DAC_SYSREF"] = {
            "source_port": 8,
            "divider": clk["AD9144_sysref"]["divider"],
        }
        map["CLKD_DAC_SYSREF"] = {
            "source_port": 7,
            "divider": clk["AD9144_sysref"]["divider"],
        }
        
        ccfg = {'map': map, 'clock': cfg["clock"]}

        # Check all clocks are mapped
        # FIXME

        # Check no source_port is mapped to more than one clock
        # FIXME

        adc, dac = self.map_jesd_structs(cfg)

        return ccfg, adc, dac

