# ADRV9040 reference evidence

`linux-standard.dts`, `linux-nls.dts`, `links.h` and `ad9528.h` are unmodified
ADI Linux sources at `22534a028813fc8e9f283b0b52dce09b05df6387` (`main`),
retaining their upstream license headers. Their upstream paths are:

- `arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-adrv904x.dts`
- `arch/arm64/boot/dts/xilinx/zynqmp-zcu102-rev10-adrv904x-nls.dts`
- `include/dt-bindings/iio/adc/adi,adrv904x.h` (`links.h`)
- `include/dt-bindings/iio/frequency/ad9528.h`

`standard.hwh` and `nls.hwh` are representative, hand-authored HWH fixtures,
not exports from Vivado or proof of a hardware build. They use upstream HDL
instance naming and the reference register windows, plus PS/concat interrupt
connectivity. Tests package each fixture into an XSA archive, exercise the
real parser, builder and merger, and mock only the SDTGen base-generation step.

Parity checks compare Linux properties after resolving the pinned macros
and translating reference labels to the HWH instance labels. FPGA `reg`
properties are checked as equivalent 32-bit reference and 64-bit SDTGen
address/size cells. FPGA output clock names follow the HWH instance labels.
