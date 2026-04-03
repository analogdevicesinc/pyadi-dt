ADI Device Tree Utilities
=========================

**pyadi-dt** is a Python library and CLI for generating, inspecting, and
managing Linux device trees for **Analog Devices** hardware — data converters,
clock distribution ICs, RF transceivers, and FPGA-based JESD204 data paths.

.. code-block:: bash

   pip install git+https://github.com/analogdevicesinc/pyadi-dt.git

Key capabilities
----------------

- **XSA-to-DTS pipeline** — Generate complete device trees from Vivado
  ``.xsa`` archives using built-in board profiles.  No manual DTS editing.
- **BoardModel API** — Construct, inspect, and modify board models
  programmatically before rendering to DTS.  Both the XSA pipeline and
  manual board classes produce the same editable ``BoardModel``.
- **Device tree inspection** — Read properties from live hardware over SSH,
  browse the tree interactively, or update SD card boot files.
- **Clock and JESD configuration** — Apply ``pyadi-jif``-solved parameters
  directly to the device tree from JSON.
- **Structural linter** — Catch unresolved phandle references, SPI
  chip-select conflicts, and clock-cell mismatches before flashing.

Supported hardware
------------------

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Converter Family
     - Platforms
   * - AD9081 / AD9082 / AD9083 (MxFE)
     - ZCU102, ZC706
   * - AD9084
     - VCU118
   * - AD9172 (DAC)
     - ZCU102
   * - ADRV9009 / ADRV9025 / ADRV9008
     - ZCU102, ZC706
   * - ADRV937x / ADRV9002
     - ZCU102, ZC706
   * - FMCDAQ2 (AD9680 + AD9144)
     - ZCU102, ZC706
   * - FMCDAQ3 (AD9680 + AD9152)
     - ZCU102, ZC706

Where to start
--------------

- **New to pyadi-dt?** See the :doc:`quickstart` for installation,
  first commands, and code examples.
- **XSA workflow?** See :doc:`examples/xsa_tutorial` for a step-by-step
  walkthrough of Vivado XSA-based generation.
- **Non-XSA workflow?** See :doc:`board_class_workflow` for generating
  device trees without Vivado (Raspberry Pi, Intel FPGA, custom boards).
- **BoardModel API?** See :doc:`api/model` for the unified board model,
  renderer, and context builders.
- **Adding a new board?** See :doc:`xsa_developer` for the pipeline
  architecture and step-by-step guide.

Links
-----

- `Source <https://github.com/analogdevicesinc/pyadi-dt>`_
- `Issue tracker <https://github.com/analogdevicesinc/pyadi-dt/issues>`_
- `EngineerZone forum <https://ez.analog.com/sw-interface-tools/f/q-a>`_
- `DeviceTree specification <http://devicetree-org.github.io/devicetree-specification>`_

Table of contents
-----------------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   quickstart
   board_class_workflow
   access
   parts
   utils
   xsa
   examples

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   xsa_developer

.. toctree::
   :maxdepth: 2
   :caption: Reference

   cli
   api/index
