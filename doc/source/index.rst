ADI Device Tree Utilities
=========================

.. caution::
  pyadi-dt is still under development and may not be stable. Feedback is welcome.

**pyadi-dt** is a Python library and CLI for generating, inspecting, and
managing Linux device trees for **Analog Devices** hardware — data converters,
clock distribution ICs, RF transceivers, and FPGA-based JESD204 data paths.

.. code-block:: bash

   pip install git+https://github.com/analogdevicesinc/pyadi-dt.git

Key capabilities
----------------

- **Declarative device API** — Compose designs out of typed Python
  devices whose fields map 1:1 to DT properties; render straight to
  DTS with no Jinja2 templates.  See :doc:`api/devices`.
- **XSA-to-DTS pipeline** — Generate complete device trees from Vivado
  ``.xsa`` archives using built-in board profiles.  No manual DTS editing.
- **Unified BoardModel** — Both the declarative API and the XSA
  pipeline converge on the same :class:`~adidt.model.BoardModel`,
  which is a single small renderer away from DTS.
- **Device tree inspection** — Read properties from live hardware over SSH,
  browse the tree interactively, or update SD card boot files.
- **Structural linter** — Catch unresolved phandle references, SPI
  chip-select conflicts, and clock-cell mismatches before flashing.

Supported hardware (declarative device layer)
---------------------------------------------

.. list-table::
   :widths: 35 30 35
   :header-rows: 1

   * - Device class
     - Part
     - Role
   * - :class:`~adidt.devices.clocks.HMC7044`
     - HMC7044
     - 14-channel JESD204B/C clock distributor
   * - :class:`~adidt.devices.clocks.AD9523_1`
     - AD9523-1
     - Clock generator / divider
   * - :class:`~adidt.devices.clocks.AD9528` / :class:`AD9528_1`
     - AD9528 / AD9528-1
     - Clock + SYSREF provider
   * - :class:`~adidt.devices.clocks.ADF4382`
     - ADF4382
     - Microwave wideband synthesizer
   * - :class:`~adidt.devices.converters.AD9081` / :class:`AD9084`
     - AD9081, AD9084
     - MxFE quad-ADC + quad-DAC
   * - :class:`~adidt.devices.converters.AD9172`
     - AD9172
     - Wideband RF DAC
   * - :class:`~adidt.devices.converters.AD9680`
     - AD9680
     - 14-bit dual-channel ADC
   * - :class:`~adidt.devices.converters.AD9144` / :class:`AD9152`
     - AD9144, AD9152
     - Quad / dual DAC
   * - :class:`~adidt.devices.transceivers.ADRV9009`
     - ADRV9009/9025/9026/9029
     - Wideband RF transceiver (single + FMComms8 dual-chip)

XSA pipeline support covers the same families plus FMCDAQ2/FMCDAQ3
composites (see :doc:`xsa`).

Where to start
--------------

- **New to pyadi-dt?** See the :doc:`quickstart` for installation,
  first commands, and a declarative-API example.
- **Declarative device API?** See :doc:`api/devices` for the full
  device catalog and composition pattern.
- **XSA workflow?** See :doc:`examples/xsa_tutorial` for a step-by-step
  walkthrough of Vivado XSA-based generation.
- **PetaLinux?** See :doc:`petalinux` for generating ``system-user.dtsi``
  files from XSA archives.
- **Adding a new device class?** See the "Writing a new device"
  section of :doc:`api/devices`.
- **Adding a new XSA board builder?** See :doc:`xsa_developer`.

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
   xsa
   petalinux
   visualization
   examples
   access
   utils

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   xsa_developer

.. toctree::
   :maxdepth: 2
   :caption: Reference

   cli
   mcp_server
   api/index
