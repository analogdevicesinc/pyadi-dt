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

Typed component classes
~~~~~~~~~~~~~~~~~~~~~~~

Components are organized into typed base classes per device category.
Each provides factory classmethods and inherits from ``ComponentModel``:

.. code-block:: python

   from adidt.model.components import ClockComponent, AdcComponent, TransceiverComponent

   clock = ClockComponent.hmc7044(spi_bus="spi1", cs=0, vcxo_hz=122_880_000, ...)
   adc = AdcComponent.ad9680(spi_bus="spi1", cs=1, clks_str="<&clk 0>", ...)
   trx = TransceiverComponent.adrv9009(spi_bus="spi0", cs=1, ...)

Available base classes and their factories:

- **ClockComponent** — ``hmc7044``, ``ad9523_1``, ``ad9528``, ``ad9545``,
  ``adf4382``, ``ltc6952``, ``ltc6953``, ``adf4371``, ``adf4377``,
  ``adf4350``, ``adf4030``
- **AdcComponent** — ``ad9680``, ``ad9088``, ``ad9467``, ``ad7768``,
  ``adaq8092``
- **DacComponent** — ``ad9144``, ``ad9152``, ``ad9172``, ``ad9739a``,
  ``ad916x``
- **TransceiverComponent** — ``ad9081``, ``ad9082``, ``ad9083``,
  ``ad9084``, ``adrv9009``
- **SensorComponent** — ``adis16495``, ``adxl345``, ``ad7124``
- **RfFrontendComponent** — ``admv1013``, ``admv1014``, ``adrf6780``,
  ``adar1000``

All base classes also provide a ``from_config(part, template, *, config)``
classmethod for template-only devices without a dedicated factory.

Standalone factory functions (backward compatible)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The original standalone functions remain available for backward
compatibility:

.. code-block:: python

   from adidt.model import components

   model = BoardModel(
       name="my_board",
       platform="rpi5",
       components=[
           components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
       ],
   )

Available: ``hmc7044``, ``ad9523_1``, ``ad9528``, ``ad9680``, ``ad9144``,
``ad9152``, ``ad9172``, ``ad9081``, ``ad9084``, ``adis16495``, ``adxl345``,
``ad7124``.

Context builders
~~~~~~~~~~~~~~~~

Lower-level functions that produce template context dicts.  Organized by
device category in submodules but importable from the top-level
``adidt.model.contexts`` package:

.. code-block:: python

   from adidt.model.contexts import build_ad9523_1_ctx

   ctx = build_ad9523_1_ctx(
       label="clk0_ad9523",
       cs=0,
       spi_max_hz=10_000_000,
       vcxo_hz=125_000_000,
   )
   # ctx is ready to pass to ad9523_1.tmpl

Context submodules:

- ``adidt.model.contexts.clocks`` — HMC7044, AD9523-1, AD9528, AD9545,
  LTC6952, LTC6953, ADF4371, ADF4377, ADF4350, ADF4030, ADF4382
- ``adidt.model.contexts.converters`` — AD9680, AD9144, AD9152, AD9172,
  AD9088, AD9467, AD7768, ADAQ8092, AD9739A, AD916x
- ``adidt.model.contexts.transceivers`` — AD9081, AD9082, AD9083, AD9084,
  ADRV9009
- ``adidt.model.contexts.sensors`` — ADIS16495, ADXL345, AD7124
- ``adidt.model.contexts.rf_frontends`` — ADMV1013, ADMV1014, ADRF6780,
  ADAR1000
- ``adidt.model.contexts.fpga`` — ADXCVR, JESD204 overlay, TPL core,
  plus ``fmt_hz`` and ``coerce_board_int`` utilities

JESD validation mixin
~~~~~~~~~~~~~~~~~~~~~

``AdcComponent``, ``DacComponent``, and ``TransceiverComponent`` include
the ``JesdDeviceMixin`` which provides:

- ``validate_jesd_params(params, direction)`` — validates JESD framing
  parameters (F, K, M, L, Np, S are positive integers)
- ``map_jesd_subclass(name)`` — maps ``"jesd204b"`` to ``1``, etc.

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

Component Classes
~~~~~~~~~~~~~~~~~

.. automodule:: adidt.model.components
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.components.base
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.components.clocks
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.components.converters
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.components.transceivers
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.components.sensors
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.components.rf_frontends
   :members:
   :undoc-members:
   :show-inheritance:

Context Builder Functions
~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: adidt.model.contexts
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.contexts.clocks
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.contexts.converters
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.contexts.transceivers
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.contexts.sensors
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.contexts.rf_frontends
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: adidt.model.contexts.fpga
   :members:
   :undoc-members:
   :show-inheritance:
