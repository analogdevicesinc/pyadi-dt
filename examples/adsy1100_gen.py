import adidt
import adijif
from pprint import pprint


vcxo = int(125e6)
cddc_dec  = 4
fddc_dec  = 2
converter_rate = int(20e9)

sys = adijif.system("ad9084_rx", "ltc6952", "xilinx", vcxo, solver="CPLEX")

sys.fpga.setup_by_dev_kit_name("adsy1100")
sys.converter.sample_clock = converter_rate / (cddc_dec * fddc_dec)
sys.converter.datapath.cddc_decimations = [cddc_dec] * 4
sys.converter.datapath.fddc_decimations = [fddc_dec] * 8
sys.converter.datapath.fddc_enabled = [True] * 8

sys.converter.clocking_option = "direct"
sys.add_pll_inline("adf4382", vcxo, sys.converter)
# sys.add_pll_sysref("adf4030", vcxo, sys.converter, sys.fpga)


sys.clock.minimize_feedback_dividers = False

mode_rx = adijif.utils.get_jesd_mode_from_params(
    sys.converter, M=4, L=8, S=1, Np=16, jesd_class="jesd204c"
)
# print(f"RX JESD Mode: {mode_rx}")
assert mode_rx
mode_rx = mode_rx[0]['mode']

sys.converter.set_quick_configuration_mode(mode_rx, "jesd204c")


# print(f"Lane rate: {sys.converter.bit_clock/1e9} Gbps")
# print(f"Needed Core clock: {sys.converter.bit_clock/66} MHz")

sys.converter._check_clock_relations()

cfg = sys.solve()

pprint(cfg)

###############################################

som = adidt.adsy1100_vu11p()

clock, fpga = som.map_clocks_to_board_layout(cfg)

converter = {"device_profile_name": "profile.bin",}
pprint(clock)
pprint(fpga)

som.gen_dt(clock=clock, fpga=fpga, converter=converter)