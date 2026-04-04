Quick Start
===========

Installation
------------

Install from the Git repository:

.. code-block:: bash

   pip install git+https://github.com/analogdevicesinc/pyadi-dt.git

For XSA pipeline support (requires Vivado ``sdtgen`` / lopper on PATH):

.. code-block:: bash

   pip install "git+https://github.com/analogdevicesinc/pyadi-dt.git#egg=adidt[xsa]"

For development with all test dependencies:

.. code-block:: bash

   pip install -e ".[dev]"

Generate a device tree from an XSA file
----------------------------------------

The fastest way to produce a device tree from a Vivado design:

.. code-block:: bash

   adidtc xsa2dt -x design.xsa --profile ad9081_zcu102 -o out/

This runs the full pipeline — ``sdtgen``, topology parsing, node building
via ``BoardModel``, and DTS merging — and writes a ``.dts`` file ready for
``dtc`` compilation.

Use ``--lint`` to run the structural linter before writing output:

.. code-block:: bash

   adidtc xsa2dt -x design.xsa --profile adrv9009_zcu102 --lint -o out/

Generate a device tree overlay from Python
-------------------------------------------

The simplest case — an ADI SPI device on a Raspberry Pi or similar
platform.  No Vivado, no XSA, no FPGA:

.. code-block:: python

   from adidt.model import BoardModel, components
   from adidt.model.renderer import BoardModelRenderer

   model = BoardModel(
       name="rpi5_imu",
       platform="rpi5",
       components=[
           components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
       ],
   )

   nodes = BoardModelRenderer().render(model)
   with open("adis16495-rpi5.dts", "w") as f:
       f.write("/dts-v1/;\n/plugin/;\n\n")
       for node_list in nodes.values():
           for node in node_list:
               f.write(node + "\n")

See :doc:`board_class_workflow` for the full walkthrough including
compilation and deployment.

Generate a device tree for an FPGA board
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For FPGA boards with clock chips and JESD204 links, use ``pyadi-jif``
to solve the clock tree and a board class to generate the DTS:

.. code-block:: python

   import adijif
   from adidt.boards.daq2 import daq2

   # Solve clock tree
   sys = adijif.system(["ad9680", "ad9144"], "ad9523_1", "xilinx", 125e6)
   sys.fpga.setup_by_dev_kit_name("zcu102")
   sys.converter[0].sample_clock = 500e6
   sys.converter[1].sample_clock = 500e6
   conf = sys.solve()

   # Generate DTS via BoardModel
   board = daq2(platform="zcu102")
   board.output_filename = "fmcdaq2_zcu102.dts"
   board.gen_dt_from_config(conf, config_source="adijif_500msps")

Edit a BoardModel before rendering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``BoardModel`` is editable after construction.  Modify any component
config, JESD parameter, or metadata before rendering:

.. code-block:: python

   from adidt.boards.daq2 import daq2
   from adidt.model.renderer import BoardModelRenderer

   board = daq2(platform="zcu102")
   model = board.to_board_model(solver_config)

   # Change clock VCXO frequency
   clock = model.get_component("clock")
   clock.config["vcxo_hz"] = 100_000_000

   # Change JESD lane count
   rx_link = model.get_jesd_link("rx")
   rx_link.link_params["L"] = 8

   # Render to DTS node strings
   nodes = BoardModelRenderer().render(model)

See :doc:`examples/board_model_usage` for more patterns.

Inspect a device tree on live hardware
---------------------------------------

Read device tree properties from a running board over SSH:

.. code-block:: bash

   adidtc -c remote_sysfs -i 192.168.2.1 prop -cp adi,ad9361 clock-output-names

.. image:: _static/media/props.gif
   :alt: props command demo

See :doc:`access` for local sysfs, remote SSH, and SD card access modes.

Configure clocks from JSON
---------------------------

Apply ``pyadi-jif``-solved clock and JESD204 parameters from a JSON file:

.. code-block:: bash

   adidtc jif --config solved_clocks.json

See :doc:`parts` for the part-layer abstractions (HMC7044, AD9523-1,
AD9528, ADRV9009).

Next steps
----------

- :doc:`examples/xsa_tutorial` — Step-by-step XSA-to-DTS walkthrough
- :doc:`board_class_workflow` — Generate device trees without Vivado
  (Raspberry Pi, Intel FPGA, custom boards)
- :doc:`examples/xsa_adijif_tutorial` — Derive JESD parameters with
  ``pyadi-jif`` before running the XSA pipeline
- :doc:`api/model` — BoardModel API reference
- :doc:`xsa_developer` — Pipeline architecture and adding new boards
