"""This shows the manual and XSA flow for the AD9081-FMC-EBZ evaluation
board on the ZCU102 platform."""

import adidt

# 1. Manually construct design

fmc = adidt.eval.ad9081_fmc()
fmc.reference_frequency = 122880000
fmc.converter.set_jesd204_mode(1, "jesd204c")
fmc.converter.adc.sample_rate = int(250e6)
fmc.converter.dac.sample_rate = int(250e6)
fmc.converter.adc.cddc_decimation = 4
fmc.converter.adc.fddc_decimation = 4
fmc.converter.dac.cduc_interpolation = 12
fmc.converter.dac.fduc_interpolation = 4

fpga = adidt.fpga.zcu102()


system = adidt.System(name="ad9081_zcu102", components=[fmc, fpga])

# Add interfaces and connections between FPGA and FMC components
## Add control busses
system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
system.connect_spi(bus_index=1, primary=fpga.spi[1], secondary=fmc.converter.spi, cs=0)

## Add JESD204 links
### ADC -> FPGA
system.add_link(
    source=fmc.converter.adc,
    sink=fpga.gt[0],
    sink_reference_clock=fmc.dev_refclk,
    sink_core_clock=fmc.core_clk_rx,
    sink_sysref=fmc.dev_sysref,
)
### FPGA -> DAC
system.add_link(
    source=fpga.gt[1],
    sink=fmc.converter.dac,
    source_reference_clock=fmc.fpga_refclk_tx,
    source_core_clock=fmc.core_clk_tx,
    sink_sysref=fmc.fpga_sysref,
)

# 2. Generate device tree source
dts = system.generate_dts()
print(dts)
