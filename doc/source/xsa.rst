XSA to Device Tree
==================

The ``adidt.xsa`` subpackage converts Vivado ``.xsa`` archives into Linux
Device Tree sources for ADI JESD204 FSM-framework designs.

Overview
--------

The pipeline performs five stages:

1. **SDT generation** – invokes ``lopper`` (``sdtgen``) as a subprocess to
   produce a base System Device Tree from the ``.xsa``.
2. **XSA parsing** – extracts the Vivado hardware handoff (``.hwh`` XML) from
   the ``.xsa`` ZIP and detects ADI AXI IPs (JESD204 controllers, clock
   generators, converters).
3. **Node building** – renders ADI-specific DTS nodes via Jinja2 templates,
   using a pyadi-jif JSON config for JESD204 parameters and HMC7044 channel
   assignments.
4. **DTS merging** – inserts the rendered nodes into the base DTS, producing
   both a standalone overlay (``.dtso``) and a fully merged (``.dts``).
5. **HTML visualization** – generates a self-contained interactive report
   with D3.js topology, clock tree, and JESD204 parameter panels.

Installation
------------

The XSA pipeline requires ``lopper`` (the Xilinx System Device Tree
generator). Install the optional dependency group:

.. code-block:: bash

   pip install "adidt[xsa]"

Usage
-----

Run the pipeline from the CLI:

.. code-block:: bash

   adidtc xsa2dt design.xsa config.json --output-dir out/

Or call the pipeline directly from Python:

.. code-block:: python

   from pathlib import Path
   from adidt.xsa.pipeline import XsaPipeline
   import json

   cfg = json.loads(Path("config.json").read_text())
   results = XsaPipeline().run(
       xsa_path=Path("design.xsa"),
       cfg=cfg,
       output_dir=Path("out/"),
   )
   print(results["merged"])   # Path to the merged .dts
   print(results["report"])   # Path to the HTML visualization

Configuration
-------------

The JSON config file supplies JESD204 link parameters and HMC7044 channel
assignments. Example for an AD9081 RX+TX design:

.. code-block:: json

   {
     "jesd": {
       "rx": { "F": 4, "K": 32 },
       "tx": { "F": 4, "K": 32 }
     },
     "clkgen": {
       "label": "axi_clkgen_0"
     },
     "hmc": {
       "rx_channel": 12,
       "tx_channel": 13
     }
   }

Supported IP Cores
------------------

The XSA parser recognises the following ADI IP cores:

============================================  ===========================
IP type (``MODTYPE``)                         Role
============================================  ===========================
``axi_jesd204_rx``, ``axi_jesd204_tx``        JESD204 FSM controllers
``axi_clkgen``                                PL clock generator
``axi_ad9081``, ``axi_ad9084``, ``axi_ad9375``  RF data converters
============================================  ===========================

Parsed topology fields
~~~~~~~~~~~~~~~~~~~~~~

``XsaTopology`` carries:

- ``fpga_part`` – full Xilinx part string (e.g. ``xczu9eg-ffvb1156-2-e``)
- ``jesd204_rx`` / ``jesd204_tx`` – list of :class:`~adidt.xsa.topology.Jesd204Instance`
- ``clkgens`` – list of :class:`~adidt.xsa.topology.ClkgenInstance`
- ``converters`` – list of :class:`~adidt.xsa.topology.ConverterInstance`

Outputs
-------

``XsaPipeline.run()`` returns a dict with the following keys:

============  ============================================
Key           Description
============  ============================================
``base_dir``  Directory containing the sdtgen output
``overlay``   ``.dtso`` overlay (ADI nodes only)
``merged``    ``.dts`` with base SDT + ADI nodes merged
``report``    Self-contained HTML visualisation report
============  ============================================

Exceptions
----------

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Exception
     - Raised when
   * - ``XsaParseError``
     - The ``.xsa`` ZIP contains no ``.hwh`` file, or the XML is malformed
   * - ``ConfigError``
     - A required JESD204 parameter (``F`` or ``K``) is missing from the config
   * - ``SdtgenNotFoundError``
     - The ``sdtgen`` / ``lopper`` binary cannot be found on ``PATH``
   * - ``SdtgenError``
     - ``sdtgen`` exits with a non-zero return code
