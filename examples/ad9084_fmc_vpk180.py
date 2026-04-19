"""AD9084-FMCA-EBZ on a Versal VPK180 platform.

Mirrors ``ad9081_fmc_zcu102.py`` for the AD9084 + VPK180 combination.
"""

import adidt

fmc = adidt.eval.ad9084_fmc()
fmc.converter.set_jesd204_mode(1, "jesd204c")
fmc.converter.adc.sample_rate = int(500e6)
fmc.converter.dac.sample_rate = int(500e6)

fpga = adidt.fpga.vpk180()

system = adidt.System(name="ad9084_vpk180", components=[fmc, fpga])

# VPK180 exposes a single SPI master; both chips hang off it.
system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=1)

# RX: ADC → FPGA.
system.add_link(
    source=fmc.converter.adc,
    sink=fpga.gt[0],
    sink_reference_clock=fmc.dev_refclk,
    sink_core_clock=fmc.core_clk_rx,
    sink_sysref=fmc.dev_sysref,
)

# TX: FPGA → DAC.
system.add_link(
    source=fpga.gt[1],
    sink=fmc.converter.dac,
    source_reference_clock=fmc.fpga_refclk_tx,
    source_core_clock=fmc.core_clk_tx,
    sink_sysref=fmc.fpga_sysref,
)

print(system.generate_dts())
