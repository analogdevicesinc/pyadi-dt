Visualization and Diagnostics
==============================

The XSA pipeline can generate interactive reports, clock-tree diagrams,
and structural lint diagnostics alongside the device tree output.

.. contents:: Contents
   :local:
   :depth: 2

HTML topology report
---------------------

The HTML report is a self-contained interactive page (no CDN or
external dependencies) built with D3.js.  It contains five panels:

1. **DTS Node Tree** — searchable list of all device tree nodes from the
   merged DTS, with highlighting for ADI-specific nodes (JESD, AD9081,
   HMC7044, etc.)
2. **XSA Match Coverage** — percentage of XSA topology IPs that appear
   in the merged DTS, with matched vs unmatched counts per category
3. **Details** — expandable tables for parsed topology (JESD RX/TX,
   converters, clockgens), clock references, and JESD data paths
4. **Clock Topology** — D3.js diagram of clock generators and their
   output nets, color-coded by component type
5. **JESD204 Data Path** — D3.js diagram showing JESD RX/TX cores,
   converters, and data flow connections with lane count annotations

Example report layout
~~~~~~~~~~~~~~~~~~~~~~

.. image:: _diagrams/svg/viz_report_layout.svg
   :alt: Example HTML topology report layout
   :align: center
   :width: 60%

Generating from Python
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from adidt.xsa.pipeline import XsaPipeline

   result = XsaPipeline().run(
       xsa_path=Path("design.xsa"),
       cfg=cfg,
       output_dir=Path("out/"),
       emit_report=True,
   )
   print(f"Report: {result['report']}")
   # out/<name>_report.html

Generating from CLI
~~~~~~~~~~~~~~~~~~~~

The ``adidtc xsa2dt`` command generates the report by default:

.. code-block:: bash

   adidtc xsa2dt -x design.xsa --profile ad9081_zcu102 -o out/
   # Opens out/ad9081_zcu102_report.html

Clock-tree diagrams
--------------------

The clock graph generator parses ``clocks``, ``clock-names``, and
``clock-output-names`` properties from the merged DTS and produces
directed graphs showing the full clock distribution tree.

Two output formats are always written:

- **Graphviz DOT** (``.dot``) — rendered to SVG automatically if
  ``dot`` is on PATH
- **D2** (``.d2``) — rendered to SVG automatically if ``d2`` is on PATH

Example: FMCDAQ2 clock tree
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following diagram shows the clock distribution for an FMCDAQ2 design
(AD9523-1 clock + AD9680 ADC + AD9144 DAC):

.. mermaid::

   flowchart LR
     subgraph PS["Processing System"]
       zynqmp_clk["zynqmp_clk\n(PS clock)"]
     end

     subgraph CLK["Clock Chip"]
       clk0_ad9523["clk0_ad9523\n(AD9523-1)"]
     end

     subgraph JESD["JESD204 Links"]
       jesd_rx["axi_ad9680_jesd204_rx"]
       jesd_tx["axi_ad9144_jesd204_tx"]
     end

     subgraph XCVR["GT Transceivers"]
       xcvr_rx["axi_ad9680_adxcvr"]
       xcvr_tx["axi_ad9144_adxcvr"]
     end

     subgraph CONV["Converters"]
       adc["adc0_ad9680\n(AD9680 ADC)"]
       dac["dac0_ad9144\n(AD9144 DAC)"]
     end

     zynqmp_clk -->|s_axi_aclk| jesd_rx
     zynqmp_clk -->|s_axi_aclk| jesd_tx
     clk0_ad9523 -->|adc_clk| adc
     clk0_ad9523 -->|adc_sysref| adc
     clk0_ad9523 -->|dac_clk| dac
     clk0_ad9523 -->|conv| xcvr_rx
     clk0_ad9523 -->|conv| xcvr_tx
     xcvr_rx -->|device_clk| jesd_rx
     xcvr_rx -->|lane_clk| jesd_rx
     xcvr_tx -->|device_clk| jesd_tx
     xcvr_tx -->|lane_clk| jesd_tx

     style PS fill:#7a3800,color:#fff
     style CLK fill:#1a3d5c,color:#fff
     style JESD fill:#1a4a20,color:#fff
     style XCVR fill:#4a1a5c,color:#fff
     style CONV fill:#5c1a1a,color:#fff

Node color coding
~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Category
     - Color
     - Examples
   * - PS clock
     - Brown
     - ``zynqmp_clk``, ``clkc``
   * - Clock chip
     - Blue
     - ``hmc7044``, ``ad9523``, ``ad9528``
   * - Transceiver (XCVR)
     - Purple
     - ``axi_ad9081_adxcvr_rx``
   * - JESD204
     - Green
     - ``axi_ad9081_jesd204_rx``
   * - Converter core
     - Red
     - ``axi_ad9081_core_rx``
   * - DMA
     - Gray
     - ``axi_ad9081_rx_dma``

Edge color coding
~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 30 20 50
   :header-rows: 1

   * - Clock Name
     - Style
     - Meaning
   * - ``device_clk``
     - Blue solid
     - Device clock from XCVR to JESD controller
   * - ``lane_clk``
     - Green solid
     - Lane clock from XCVR to JESD controller
   * - ``conv``
     - Orange solid
     - Reference clock from clock chip to XCVR
   * - ``sampl_clk``
     - Purple solid
     - Sampling clock from PHY to TPL core
   * - ``s_axi_aclk``
     - Gray dashed
     - AXI register access clock (PS → peripherals)

Example DOT output
~~~~~~~~~~~~~~~~~~~

.. code-block:: dot

   digraph clock_topology {
       label="fmcdaq2 — clock topology";
       rankdir=LR;
       node [style="filled,rounded" fontname="monospace"];

       zynqmp_clk [label="zynqmp_clk" fillcolor="#7a3800"];
       clk0_ad9523 [label="clk0_ad9523\n(ad9523-1)" fillcolor="#1a3d5c"];
       axi_ad9680_adxcvr [label="axi_ad9680_adxcvr" fillcolor="#4a1a5c"];
       axi_ad9680_jesd204_rx [label="axi_ad9680_jesd204_rx" fillcolor="#1a4a20"];
       adc0_ad9680 [label="adc0_ad9680\n(ad9680)" fillcolor="#5c1a1a"];

       clk0_ad9523 -> adc0_ad9680 [label="adc_clk"];
       clk0_ad9523 -> axi_ad9680_adxcvr [label="conv"];
       axi_ad9680_adxcvr -> axi_ad9680_jesd204_rx [label="device_clk"];
       zynqmp_clk -> axi_ad9680_jesd204_rx [label="s_axi_aclk" style=dashed];
   }

Generating from Python
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   result = XsaPipeline().run(
       xsa_path=Path("design.xsa"),
       cfg=cfg,
       output_dir=Path("out/"),
       emit_clock_graphs=True,
   )
   print(f"DOT: {result['clock_dot']}")
   print(f"D2:  {result['clock_d2']}")
   # SVG files present if rendering tools are on PATH:
   if "clock_dot_svg" in result:
       print(f"SVG: {result['clock_dot_svg']}")

Installing rendering tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~

DOT and D2 are optional — the ``.dot`` and ``.d2`` text files are
always written.  Install the tools to get SVG output:

.. code-block:: bash

   # Graphviz (DOT → SVG)
   sudo apt install graphviz

   # D2 (D2 → SVG)
   curl -fsSL https://d2lang.com/install.sh | sh -s --

DTS structural linter
----------------------

The built-in linter checks the generated DTS for structural issues
before flashing to hardware.

Checks include:

- Unresolved phandle references (``<&missing_label>``)
- SPI chip-select conflicts (two devices at the same CS on one bus)
- Clock cell count mismatches (``#clock-cells`` vs clock phandle args)
- Missing ``compatible`` strings
- Duplicate node labels

Example lint output
~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "diagnostics": [
       {
         "severity": "error",
         "rule": "unresolved-phandle",
         "node": "&axi_adrv9009_core_rx_obs",
         "message": "Label 'axi_adrv9009_core_rx_obs' not found in base DTS"
       },
       {
         "severity": "warning",
         "rule": "spi-cs-conflict",
         "node": "&spi0",
         "message": "Duplicate chip-select 0 on spi0 bus"
       }
     ],
     "summary": {
       "errors": 1,
       "warnings": 1,
       "info": 0,
       "total": 2
     }
   }

Generating from Python
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   result = XsaPipeline().run(
       xsa_path=Path("design.xsa"),
       cfg=cfg,
       output_dir=Path("out/"),
       lint=True,
       strict_lint=True,  # Raises DtsLintError on errors
   )
   print(f"Diagnostics: {result['diagnostics']}")
   # out/<name>_diagnostics.json

Generating from CLI
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Run with lint warnings
   adidtc xsa2dt -x design.xsa --profile adrv9009_zcu102 --lint -o out/

   # Fail on lint errors
   adidtc xsa2dt -x design.xsa --profile adrv9009_zcu102 --strict-lint -o out/

Combining all outputs
----------------------

Enable everything at once:

.. code-block:: python

   result = XsaPipeline().run(
       xsa_path=Path("design.xsa"),
       cfg=cfg,
       output_dir=Path("out/"),
       emit_report=True,
       emit_clock_graphs=True,
       lint=True,
   )

This produces:

.. image:: _diagrams/svg/viz_outputs.svg
   :alt: XsaPipeline output artifacts
   :align: center
   :width: 60%
