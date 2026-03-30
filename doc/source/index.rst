ADI Device Tree Utilities
=========================

**pyadi-dt** is a Python library and CLI for generating, inspecting, and
managing Linux device trees for **Analog Devices** hardware — data converters,
clock distribution ICs, RF transceivers, and FPGA-based JESD204 data paths.

.. code-block:: bash

   pip install git+https://github.com/analogdevicesinc/pyadi-dt.git

What pyadi-dt does
------------------

**Generate device trees from Vivado XSA files.**
Point the ``adidtc xsa2dt`` command at a Vivado ``.xsa`` archive and a board
profile.  The pipeline parses the hardware description, renders ADI-specific
DTS nodes via Jinja2 templates, and produces a merged ``.dts`` ready for
``dtc`` compilation — no manual DTS editing needed.

.. code-block:: bash

   adidtc xsa2dt -x design.xsa --profile ad9084_vcu118 -o out/

**Inspect and modify device trees on live hardware.**
Read properties from a running board over SSH, browse the device tree
interactively, or update SD card boot files.

.. code-block:: bash

   adidtc -c remote_sysfs -i 192.168.2.1 prop -cp adi,ad9361 clock-output-names

.. image:: _static/media/props.gif
   :alt: props command demo

**Configure clock chips and converters from JSON.**
Apply ``pyadi-jif``-solved clock and JESD204 parameters directly to the
device tree — update HMC7044 channel dividers, AD9081 datapath settings,
or AD9528 PLL configuration with a single command.

.. code-block:: bash

   adidtc jif --config solved_clocks.json

**Validate generated device trees.**
Run the built-in structural linter to catch unresolved phandle references,
SPI chip-select conflicts, clock-cell mismatches, and missing compatible
strings before flashing hardware.

.. code-block:: bash

   adidtc xsa2dt -x design.xsa --profile adrv9009_zcu102 --lint -o out/

Supported hardware
------------------

pyadi-dt includes built-in profiles for the following ADI evaluation boards
and FPGA platforms:

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

See :doc:`xsa` for the complete profile reference table with JESD parameter
and board config details.

Where to start
--------------

- **First time?** Start with the :doc:`examples/xsa_tutorial` for a
  step-by-step walkthrough of XSA-based device tree generation.
- **Inspecting a live board?** See :doc:`access` for the different access
  models (local sysfs, remote SSH, SD card).
- **Configuring clock chips?** See :doc:`parts` for the part-layer
  abstractions (HMC7044, AD9523-1, AD9528, ADRV9009).
- **Adding a new board?** See :doc:`xsa_developer` for the pipeline
  architecture, builder pattern, and step-by-step guide.

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
