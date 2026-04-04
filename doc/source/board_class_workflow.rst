Device Tree Generation
======================

There are two paths available for device tree generation.  The first path is to use the ``BoardModel`` API to generate device tree overlays directly from Python. The second path is to use the ``BoardModel`` API to generate device tree overlays from a Vivado ``.xsa`` file. If you are connecting an ADI device to a Raspberry Pi, BeagleBone, Intel FPGA, or
any platform that does not use Vivado, you can generate device tree
overlays directly from Python using the ``BoardModel`` API.

This guide walks through the simplest case — an ADIS16495 IMU on a
Raspberry Pi — then shows how the same approach scales to more complex
boards with clock chips, JESD204 links, and FPGA transceivers. It is recommened to follow the XSA workflow if you are using Vivado, but it is not required. See :doc:`xsa` for more information.

.. contents:: Contents
   :local:
   :depth: 2

Example: ADIS16495 IMU on Raspberry Pi
---------------------------------------

The `ADIS16495 <https://www.analog.com/adis16495>`_ is a 6-DOF inertial
measurement unit connected via SPI.  Its device tree node is simple:
a compatible string, SPI mode flags, and an interrupt GPIO.

Step 1: Build a BoardModel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from adidt.model import BoardModel, components

   model = BoardModel(
       name="rpi5_adis16495",
       platform="rpi5",
       components=[
           components.adis16495(
               spi_bus="spi0",
               cs=0,
               gpio_label="gpio",
               interrupt_gpio=25,
           ),
       ],
   )

The ``components`` module provides pre-configured factories for each
supported device — no need to specify template filenames or role strings.

That is the entire model.  No JESD links, no FPGA config, no clock chip —
just one SPI device.

Step 2: Render to DTS
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from adidt.model.renderer import BoardModelRenderer

   nodes = BoardModelRenderer().render(model)
   overlay_content = nodes["converters"][0]
   print(overlay_content)

Output:

.. code-block:: dts

   &spi0 {
       status = "okay";
       #address-cells = <1>;
       #size-cells = <0>;
       imu0: adis16495@0 {
           compatible = "adi,adis16495-1";
           reg = <0>;
           spi-max-frequency = <2000000>;
           spi-cpol;
           spi-cpha;
           interrupt-parent = <&gpio>;
           interrupts = <25 IRQ_TYPE_EDGE_FALLING>;
       };
   };

Step 3: Write to a file
~~~~~~~~~~~~~~~~~~~~~~~~~

Wrap the overlay in DTS headers and write it out:

.. code-block:: python

   with open("adis16495-rpi5.dts", "w") as f:
       f.write("/dts-v1/;\n/plugin/;\n\n")
       for node_list in nodes.values():
           for node in node_list:
               f.write(node + "\n")

Step 4: Compile and deploy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Compile the overlay
   dtc -@ -I dts -O dtb -o adis16495-rpi5.dtbo adis16495-rpi5.dts

   # Copy to the RPi boot partition
   sudo cp adis16495-rpi5.dtbo /boot/overlays/

   # Enable in config.txt
   echo "dtoverlay=adis16495-rpi5" | sudo tee -a /boot/config.txt

   # Reboot
   sudo reboot

After reboot, verify the device appears:

.. code-block:: bash

   ls /sys/bus/iio/devices/
   cat /sys/bus/iio/devices/iio:device0/name
   # adis16495-1

Editing the model before rendering
------------------------------------

The ``BoardModel`` is a plain Python dataclass.  Change any field before
rendering:

.. code-block:: python

   # Change interrupt GPIO pin
   imu = model.components[0]
   imu.config["interrupt_gpio"] = 17

   # Change SPI chip select
   imu.config["cs"] = 1
   imu.spi_cs = 1

   # Use a different ADIS variant
   imu.config["compatible"] = "adi,adis16497-3"
   imu.config["device"] = "adis16497"

   # Re-render with changes
   nodes = BoardModelRenderer().render(model)

Multiple devices on one board
------------------------------

Add more components to the same model.  Devices on the same SPI bus are
automatically grouped:

.. code-block:: python

   model = BoardModel(
       name="rpi5_multi",
       platform="rpi5",
       components=[
           components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
           components.adis16495(
               spi_bus="spi0", cs=1, label="imu1", interrupt_gpio=24,
           ),
       ],
   )

Both devices appear inside the same ``&spi0 { ... }`` block in the
rendered output.

Scaling up: FPGA boards with JESD204
--------------------------------------

For boards with clock chips, high-speed converters, and JESD204 links,
the same ``BoardModel`` structure scales by adding more components and
``JesdLinkModel`` entries.  The existing board classes handle this
complexity:

.. code-block:: python

   from adidt.boards.daq2 import daq2

   board = daq2(platform="zcu102")
   model = board.to_board_model(solver_config)
   # model.components: AD9523-1 clock, AD9680 ADC, AD9144 DAC
   # model.jesd_links: RX link, TX link

See :doc:`examples/board_model_usage` for detailed examples with
``daq2``, ``ad9081_fmc``, ``adrv9009_fmc``, and ``ad9084_fmc``.

For the XSA pipeline workflow (Vivado-based), see :doc:`examples/xsa_tutorial`.

Available components
---------------------

The ``adidt.model.components`` module provides factory functions for each
supported device.  Import and use directly — no template filenames needed:

.. code-block:: python

   from adidt.model import components

**Simple SPI devices:**

- ``components.adis16495(spi_bus, cs, ...)`` — ADIS16495/16497 IMU

**Clock chips:**

- ``components.hmc7044(spi_bus, cs, ...)`` — HMC7044 clock distributor
- ``components.ad9523_1(spi_bus, cs, ...)`` — AD9523-1 clock generator
- ``components.ad9528(spi_bus, cs, ...)`` — AD9528 clock generator

**ADCs / DACs:**

- ``components.ad9680(spi_bus, cs, ...)`` — AD9680 ADC
- ``components.ad9144(spi_bus, cs, ...)`` — AD9144 DAC
- ``components.ad9152(spi_bus, cs, ...)`` — AD9152 DAC
- ``components.ad9172(spi_bus, cs, ...)`` — AD9172 RF DAC

**Transceivers:**

- ``components.ad9081(spi_bus, cs, ...)`` — AD9081 MxFE
- ``components.ad9084(spi_bus, cs, ...)`` — AD9084 RX transceiver

Each factory accepts device-specific keyword arguments (forwarded to the
underlying context builder).  See :doc:`api/model` for the full API
reference.
