XSA Template Reference
======================

The ``adidt/templates/xsa/`` directory contains Jinja2 templates that render
individual DTS nodes for ADI components.  Each template produces one SPI
device child node, one AXI overlay node, or a pair of related nodes.

Templates are rendered by ``NodeBuilder._render(name, context)`` where
*context* is a dict (or dataclass with ``as_dict()``) whose keys match the
Jinja2 variables in the template.  See :doc:`../xsa_developer` for the
template composition architecture.

Templates marked **UNTESTED** were generated from Linux kernel devicetree
bindings and have not been validated on hardware.


High-Speed Data Converters (JESD204)
------------------------------------

These templates render SPI device nodes for ADI data converters that use
JESD204B or JESD204C serial data interfaces.  They include ``jesd204-device``
properties and link to the JESD204 FSM framework.

.. list-table::
   :widths: 20 25 55
   :header-rows: 1

   * - Template
     - Compatible
     - Description
   * - ``ad9081_mxfe.tmpl``
     - ``adi,ad9081``
     - AD9081 MxFE with full TX DAC / RX ADC sub-tree, JESD204 link config, and converter-select properties.  Tested.
   * - ``ad9084.tmpl``
     - ``adi,ad9084``
     - AD9084 dual-link converter with firmware loading, lane mappings, HSCI, and side-B TPL support.  Tested.
   * - ``ad9088.tmpl``
     - ``adi,ad9088``
     - AD9088 (AD9084 driver variant) MxFE with clock provider outputs and JESD204 link configuration.  **UNTESTED.**
   * - ``ad9083.tmpl``
     - ``adi,ad9083``
     - AD9083 8-channel ADC with JESD204B/C support and NCO/decimation configuration.  **UNTESTED.**
   * - ``ad916x.tmpl``
     - ``adi,ad9161`` through ``adi,ad9166``
     - AD916x wideband DAC family with JESD204 transport parameters and interpolation setting.  **UNTESTED.**
   * - ``ad9680.tmpl``
     - ``adi,ad9680``
     - AD9680 ADC with optional SPI 3-wire mode, 1 or 3 clock inputs, and JESD204 link properties.  Tested.
   * - ``ad9144.tmpl``
     - ``adi,ad9144``
     - AD9144 DAC with clock reference and JESD204 link properties.  Tested.
   * - ``ad9152.tmpl``
     - ``adi,ad9152``
     - AD9152 DAC (FMCDAQ3) with JESD link mode and SPI CPOL/CPHA.  Tested.
   * - ``ad9172.tmpl``
     - ``adi,ad9172``
     - AD9172 DAC with interpolation, link mode, and clock output divider.  Tested.
   * - ``adrv9009.tmpl``
     - ``adi,adrv9009`` / ``adi,adrv9025``
     - ADRV9009/9025 RF transceiver with optional dual-chip FMComms8 layout.  Tested.
   * - ``ad9467.tmpl``
     - ``adi,ad9467`` and variants
     - AD9467/AD9265/AD9434/AD9643/AD9649/AD9652 high-speed ADC family.  **UNTESTED.**
   * - ``ad9739a.tmpl``
     - ``adi,ad9739a``
     - AD9739a RF DAC with configurable full-scale current.  **UNTESTED.**


High-Speed DACs (Non-JESD)
--------------------------

.. list-table::
   :widths: 20 25 55
   :header-rows: 1

   * - Template
     - Compatible
     - Description
   * - ``ad9739a.tmpl``
     - ``adi,ad9739a``
     - AD9739a RF DAC with configurable full-scale current output.  **UNTESTED.**


Frequency Synthesizers (PLLs)
-----------------------------

These templates render SPI device nodes for PLL frequency synthesizers.
Most are clock providers (``#clock-cells``) whose outputs feed converter
device clocks or FPGA reference clocks.

.. list-table::
   :widths: 20 25 55
   :header-rows: 1

   * - Template
     - Compatible
     - Description
   * - ``adf4382.tmpl``
     - ``adi,adf4382`` / ``adi,adf4382a``
     - Microwave wideband PLL with charge pump, power-up frequency, and 3-wire SPI support.  Clock provider.  **UNTESTED.**
   * - ``adf4377.tmpl``
     - ``adi,adf4377`` / ``adi,adf4378``
     - Microwave PLL with muxout selection and GPIO enable pins.  **UNTESTED.**
   * - ``adf4371.tmpl``
     - ``adi,adf4371`` / ``adi,adf4372``
     - Wideband PLL with multi-channel output, charge pump tuning, and mute-till-lock.  Clock provider.  **UNTESTED.**
   * - ``adf4350.tmpl``
     - ``adi,adf4350`` / ``adi,adf4351``
     - Wideband PLL with channel spacing, output power, and extensive PLL tuning properties.  Clock provider.  **UNTESTED.**
   * - ``adf4030.tmpl``
     - ``adi,adf4030``
     - 10-channel precision synchronizer with per-channel delay and VCO/BSYNC configuration.  Clock provider.  **UNTESTED.**


Clock Generators and Distributors
---------------------------------

.. list-table::
   :widths: 20 25 55
   :header-rows: 1

   * - Template
     - Compatible
     - Description
   * - ``hmc7044.tmpl``
     - ``adi,hmc7044``
     - HMC7044 clock distribution IC with PLL1/PLL2 configuration, up to 14 output channels, JESD204 sysref provider, and GPI/GPO controls.  Tested.
   * - ``ad9523_1.tmpl``
     - ``adi,ad9523-1``
     - AD9523-1 clock generator (FMCDAQ2) with 8 channels and optional GPIO lines.  Tested.
   * - ``ad9528.tmpl``
     - ``adi,ad9528``
     - AD9528 clock generator (FMCDAQ3) with signal-source and sysref channel properties.  Tested.
   * - ``ad9528_1.tmpl``
     - ``adi,ad9528``
     - AD9528-1 variant (ADRV9009 standard path) with ADRV9009-specific PLL properties.  Tested.
   * - ``ad9545.tmpl``
     - ``adi,ad9545``
     - AD9545 quad-input DPLL network clock with reference frequency and optional crystal/doubler modes.  **UNTESTED.**
   * - ``ltc6952.tmpl``
     - ``adi,ltc6952`` / ``adi,ltc6953``
     - LTC6952 ultralow-jitter clock distribution with per-channel divider, digital delay, and analog delay.  **UNTESTED.**


RF Front-End Components
-----------------------

.. list-table::
   :widths: 20 25 55
   :header-rows: 1

   * - Template
     - Compatible
     - Description
   * - ``admv1013.tmpl``
     - ``adi,admv1013``
     - Microwave upconverter with IQ/IF input mode, quad SE mode, and detector enable.  Clock provider.  **UNTESTED.**
   * - ``admv1014.tmpl``
     - ``adi,admv1014``
     - Microwave downconverter with IQ/IF input mode, P1dB compensation, and detector enable.  **UNTESTED.**
   * - ``adrf6780.tmpl``
     - ``adi,adrf6780``
     - Microwave upconverter with LO enable/doubler/PPF, IQ/IF mode selection, and VGA buffer control.  Clock provider.  **UNTESTED.**
   * - ``adar1000.tmpl``
     - ``adi,adar1000``
     - X/Ku band beamformer with multi-device sub-nodes.  **UNTESTED.**


Data Acquisition
----------------

.. list-table::
   :widths: 20 25 55
   :header-rows: 1

   * - Template
     - Compatible
     - Description
   * - ``ad7768.tmpl``
     - ``adi,ad7768`` / ``adi,ad7768-4``
     - 8-/4-channel 24-bit sigma-delta ADC with DMA and configurable data lines.  **UNTESTED.**
   * - ``adaq8092.tmpl``
     - ``adi,adaq8092``
     - Dual-channel 14-bit 105 MSPS DAQ module.  **UNTESTED.**


FPGA AXI Peripherals
---------------------

These templates render overlay nodes for FPGA IP cores in the Vivado
block design.  They add ADI-specific properties to nodes that ``sdtgen``
already defined with Xilinx generic compatible strings.

.. list-table::
   :widths: 20 25 55
   :header-rows: 1

   * - Template
     - Compatible
     - Description
   * - ``clkgen.tmpl``
     - ``adi,axi-clkgen-2.00.a``
     - AXI clock generator overlay with clock output names.  Tested.
   * - ``adxcvr.tmpl``
     - ``adi,axi-adxcvr-1.0``
     - GT transceiver overlay with PLL select, clock references, and optional LPM enable.  Tested.
   * - ``jesd204_overlay.tmpl``
     - ``adi,axi-jesd204-rx-1.0`` / ``-tx-``
     - JESD204 controller overlay with framing parameters and JESD204 input chain.  Tested.
   * - ``jesd204_fsm.tmpl``
     - ``adi,axi-jesd204-rx-1.0`` / ``-tx-``
     - Generic JESD204 FSM overlay used by the generic rendering path.  Tested.
   * - ``tpl_core.tmpl``
     - (varies by board)
     - Transport protocol layer core overlay with DMA link and converter association.  Tested.
   * - ``axi_ad9081.tmpl``
     - ``adi,ad9081``
     - AXI AD9081 MxFE PL core overlay.  Tested.


Utility Templates
-----------------

.. list-table::
   :widths: 20 55
   :header-rows: 1

   * - Template
     - Description
   * - ``_jesd_macros.tmpl``
     - Jinja2 macros for JESD204 device properties (``jesd204-device``, ``#jesd204-cells``, ``jesd204-inputs``).  Imported by other templates.
