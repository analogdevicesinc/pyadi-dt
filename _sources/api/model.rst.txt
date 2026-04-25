Board Model
===========

``adidt.model`` holds the dataclasses that carry a fully-assembled
design on its way to DTS output.  Both the XSA pipeline and the
declarative :mod:`adidt.system` API produce the same
:class:`BoardModel`, which :class:`BoardModelRenderer` then assembles
into DTS strings.

Pipeline
--------

.. code-block:: text

   XSA Pipeline                        Declarative System
   ─────────────                       ──────────────────
   XsaPipeline.run()                   adidt.System(name, components)
     └─ AD9081Builder                    └─ system.connect_spi(...)
          .build_model()                    system.add_link(...)
              │                                 │
              └──────────────┬──────────────────┘
                             ▼
                        BoardModel
                   (components + jesd_links)
                             │
                             ▼
                    BoardModelRenderer
                          .render()
                             │
                             ▼
              {clkgens, jesd204_rx/tx, converters}
                             │
                             ▼
                         DTS output

Components and JESD links carry pre-rendered DTS strings (produced by
the declarative device classes in :mod:`adidt.devices`).  The renderer
groups components by SPI bus, wraps each group in ``&spi_bus { ... };``,
and concatenates per-direction JESD overlays.  No Jinja2 involved.

Classes
-------

.. autoclass:: adidt.model.BoardModel
   :no-members:

.. autoclass:: adidt.model.ComponentModel
   :no-members:

.. autoclass:: adidt.model.JesdLinkModel
   :no-members:

.. autoclass:: adidt.model.FpgaConfig
   :no-members:

.. autoclass:: adidt.model.renderer.BoardModelRenderer
   :members:

Fields of note
--------------

- ``ComponentModel.rendered`` — pre-rendered DTS string for this
  component.  Declarative devices always populate this; the renderer
  inserts it verbatim into its SPI-bus group.
- ``JesdLinkModel.{xcvr,jesd_overlay,tpl_core}_rendered`` — the three
  FPGA-side IP overlays for a single link.  All three are produced by
  :mod:`adidt.devices.fpga_ip` devices.
- ``JesdLinkModel.{xcvr,jesd_overlay,tpl_core}_config`` — legacy
  dict-typed fields kept for dict-based tests; unused by the current
  rendering path.
