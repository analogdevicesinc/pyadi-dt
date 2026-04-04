Board Model Module
==================

The ``adidt.model`` package provides the unified ``BoardModel`` abstraction
that both the manual board-class workflow and the XSA pipeline produce.
A single ``BoardModelRenderer`` renders any ``BoardModel`` to DTS using
per-component Jinja2 templates.

Overview
--------

A ``BoardModel`` describes the complete hardware composition of a board:
what components exist, how they connect via JESD204 links, and what FPGA
configuration applies.  Three workflows converge on this model:

.. code-block:: text

   XSA Pipeline                Manual Board Class         Direct Construction
   ─────────────               ──────────────────         ────────────────────
   XsaPipeline.run()           daq2.to_board_model(cfg)   BoardModel(name=...,
     └─ AD9081Builder            ad9081_fmc                  components=[...],
          .build_model()           .to_board_model(cfg)       jesd_links=[...])
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       ▼
                                  BoardModel
                                       │
                              BoardModelRenderer
                                  .render()
                                       │
                                       ▼
                              dict[str, list[str]]
                              (DTS node strings)
                                       │
                                  DtsMerger
                                  .merge()
                                       │
                                       ▼
                                .dts / .dtso files

The model is **editable** after construction.  You can modify component
configs, JESD parameters, or metadata before rendering:

.. code-block:: python

   from adidt.xsa.builders.fmcdaq2 import FMCDAQ2Builder
   from adidt.model.renderer import BoardModelRenderer

   # Build from XSA topology
   model = FMCDAQ2Builder().build_model(topology, cfg, "zynqmp_clk", 71, "gpio")

   # Edit before rendering
   clock = model.get_component("clock")
   clock.config["vcxo_hz"] = 100_000_000

   # Render to DTS
   nodes = BoardModelRenderer().render(model)

Supported boards
~~~~~~~~~~~~~~~~

All six XSA builders produce ``BoardModel`` instances:

.. list-table::
   :widths: 25 20 55
   :header-rows: 1

   * - Builder
     - Clock Chip
     - Converters
   * - ``FMCDAQ2Builder``
     - AD9523-1
     - AD9680 (ADC) + AD9144 (DAC)
   * - ``FMCDAQ3Builder``
     - AD9528
     - AD9680 (ADC) + AD9152 (DAC)
   * - ``AD9172Builder``
     - HMC7044
     - AD9172 (DAC)
   * - ``AD9081Builder``
     - HMC7044
     - AD9081 MxFE (ADC + DAC)
   * - ``ADRV9009Builder``
     - AD9528
     - ADRV9009 (transceiver, RX + TX + ORX)
   * - ``AD9084Builder``
     - HMC7044 + ADF4382
     - AD9084 (RX transceiver)

Board classes with ``to_board_model()``:

- ``adidt.boards.daq2`` (ZCU102, ZC706)

Component factories
~~~~~~~~~~~~~~~~~~~~

The easiest way to create components.  Each factory returns a
pre-configured ``ComponentModel`` — no template filenames needed:

.. code-block:: python

   from adidt.model import BoardModel, components

   model = BoardModel(
       name="my_board",
       platform="rpi5",
       components=[
           components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
       ],
   )

Available factories (``from adidt.model import components``):

- **Simple SPI:** ``components.adis16495`` — ADIS16495/16497 IMU
- **Clock chips:** ``components.hmc7044``, ``components.ad9523_1``,
  ``components.ad9528``
- **ADCs / DACs:** ``components.ad9680``, ``components.ad9144``,
  ``components.ad9152``, ``components.ad9172``
- **Transceivers:** ``components.ad9081``, ``components.ad9084``

Context builders
~~~~~~~~~~~~~~~~

Lower-level functions that produce template context dicts.  Use these
when you need full control over every field, or when no factory exists
for your device:

.. code-block:: python

   from adidt.model.contexts import build_ad9523_1_ctx

   ctx = build_ad9523_1_ctx(
       label="clk0_ad9523",
       cs=0,
       spi_max_hz=10_000_000,
       vcxo_hz=125_000_000,
   )
   # ctx is ready to pass to ad9523_1.tmpl

API Reference
-------------

Board Model
~~~~~~~~~~~

.. automodule:: adidt.model.board_model
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Renderer
~~~~~~~~

.. automodule:: adidt.model.renderer
   :members:
   :undoc-members:
   :show-inheritance:

Context Builder Functions
~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: adidt.model.contexts
   :members:
   :undoc-members:
   :show-inheritance:

Component Factories
~~~~~~~~~~~~~~~~~~~

.. automodule:: adidt.model.components
   :members:
   :undoc-members:
   :show-inheritance:
