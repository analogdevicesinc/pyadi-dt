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

Nodes are color-coded:

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
     - Orange
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

Edges are color-coded by clock name:

- ``device_clk`` — blue
- ``lane_clk`` — green
- ``conv`` — orange
- ``sampl_clk`` — purple
- ``s_axi_aclk`` — gray dashed

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

The diagnostics JSON file contains severity, rule, node path, and
message for each finding.

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
   # result keys:
   # "merged"         — merged .dts file
   # "overlay"        — .dtso overlay file
   # "base_dir"       — sdtgen output directory
   # "report"         — interactive HTML report
   # "clock_dot"      — Graphviz DOT clock tree
   # "clock_d2"       — D2 clock tree
   # "clock_dot_svg"  — SVG (if dot on PATH)
   # "clock_d2_svg"   — SVG (if d2 on PATH)
   # "diagnostics"    — lint diagnostics JSON
