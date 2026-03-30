XSA Pipeline — Developer Guide
================================

This document explains the internal architecture of the XSA pipeline, how
Jinja2 templates are used for DTS generation, and how to add support for new
components and boards.

.. contents:: Contents
   :local:
   :depth: 2

Architecture
------------

The XSA pipeline is composed of six loosely coupled stages.  Each stage
operates on well-defined inputs and produces file or data-structure outputs
that feed the next stage.

.. code-block:: text

   XSA (ZIP)
     │
     ├─▶ XsaParser ──────────────────▶ XsaTopology
     │    (topology.py)                  (dataclass)
     │
     ├─▶ sdtgen / lopper ──────────▶ base DTS artifacts
     │    (sdtgen.py)
     │
     ├─▶ NodeBuilder ◀──── cfg dict ─▶ dict[str, list[str]]
     │    (node_builder.py)               ADI DTS node strings
     │
     ├─▶ DtsMerger ────────────────▶ .dtso overlay + .dts merged
     │    (merger.py)
     │
     ├─▶ HtmlVisualizer ───────────▶ interactive HTML report
     │    (visualizer.py)
     │
     └─▶ ClockGraphGenerator ──────▶ .dot + .d2 (+ SVG when tools present)
          (clock_graph.py)

``XsaPipeline.run()`` in ``pipeline.py`` wires all stages together and returns
a ``dict[str, Path]`` of artifact paths.  Each stage class can also be used
independently.

Key data models
~~~~~~~~~~~~~~~

``XsaTopology`` (``topology.py``)
   Populated by ``XsaParser.parse()``.  Carries lists of
   ``Jesd204Instance``, ``ClkgenInstance``, ``ConverterInstance``, and
   ``SignalConnection`` objects plus ``fpga_part``.

   The helper methods ``is_fmcdaq2_design()``, ``is_fmcdaq3_design()``,
   ``inferred_converter_family()``, and ``inferred_platform()`` encapsulate
   topology-level detection logic so that ``NodeBuilder`` does not have to
   re-parse names in multiple places.

``cfg`` dict
   A plain Python dict derived from a JSON board profile.  JESD204 parameters
   live under ``cfg["jesd"]["rx"]`` / ``cfg["jesd"]["tx"]``; board-wiring
   overrides live under family-specific keys such as ``cfg["ad9081_board"]``,
   ``cfg["adrv9009_board"]``, etc.  Profile loading and merging is handled by
   ``profiles.py``.

NodeBuilder internals
---------------------

``NodeBuilder`` (``node_builder.py``) is the heart of the pipeline.  It owns
all Jinja2 template rendering and all board-specific DTS node assembly.

Entry point
~~~~~~~~~~~

.. code-block:: python

   result = NodeBuilder().build(topology, cfg)
   # Returns:
   # {
   #   "clkgens":    [str, ...],   # axi-clkgen overlay nodes
   #   "jesd204_rx": [str, ...],   # generic JESD RX overlay nodes
   #   "jesd204_tx": [str, ...],   # generic JESD TX overlay nodes
   #   "converters": [str, ...],   # all board-specific nodes
   # }

``build()`` first handles generic JESD and clkgen nodes (used by designs that
do not have a dedicated board builder), then delegates to the five board
builders for the designs that need richer SPI-device and clock-chip content:

- ``_build_ad9081_nodes()`` — AD9081/AD9082 MXFE designs
- ``_build_ad9084_nodes()`` — AD9084 "apollo" dual-link designs (ADF4382 +
  HMC7044 + HSCI + per-link JESD device clocks)
- ``_build_adrv9009_nodes()`` — ADRV9009/9025 designs, including FMComms8
- ``_build_fmcdaq2_nodes()`` — FMCDAQ2 (AD9523-1 + AD9680 + AD9144)
- ``_build_fmcdaq3_nodes()`` — FMCDAQ3 (AD9528 + AD9680 + AD9152)
- ``_build_ad9172_nodes()`` — AD9172 (HMC7044 + AD9172)

Each board builder returns an empty list when its topology check fails, so all
five are called unconditionally in ``build()``.

Platform-aware register format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MicroBlaze platforms (VCU118) use 32-bit addressing (``#address-cells = <1>``),
while ZynqMP platforms use 64-bit (``#address-cells = <2>``).  Templates must
emit ``reg`` properties in the correct cell format.

``NodeBuilder`` exposes two Jinja2 globals — ``reg_addr()`` and ``reg_size()``
— that format addresses and sizes according to the detected platform:

.. code-block:: jinja

   reg = <{{ reg_addr(instance.base_addr) }} {{ reg_size(0x10000) }}>;

On VCU118 this renders as ``reg = <0x44ad0000 0x10000>`` (2 cells), and on
ZCU102 as ``reg = <0x0 0x44ad0000 0x0 0x10000>`` (4 cells).

The platform is detected from the FPGA part string in the XSA topology via
``inferred_platform()``.  32-bit platforms are listed in
``NodeBuilder._32BIT_PLATFORMS``.

sdtgen postprocessing (MicroBlaze)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``SdtgenRunner`` applies several fixups to the sdtgen-generated DTS for
MicroBlaze/VCU118 targets that are required for Linux boot:

- **CPU cluster rename**: ``cpus_microblaze@0`` → ``cpus`` (Linux
  ``of_find_node_by_path("/cpus")`` requires exact name match).
- **DDR4 memory node**: Adds ``device_type = "memory"`` and collapses 4-cell
  ``reg`` to 2-cell format when ``#address-cells = <1>``.
- **earlycon bootargs**: Injects ``bootargs = "earlycon"`` into the ``chosen``
  node so the kernel produces serial output from early boot.

Jinja2 environment
~~~~~~~~~~~~~~~~~~

The Jinja2 ``Environment`` is a ``@cached_property`` on ``NodeBuilder``:

.. code-block:: python

   @cached_property
   def _env(self) -> Environment:
       return Environment(
           loader=FileSystemLoader(str(Path(__file__).parent.parent / "templates" / "xsa")),
           keep_trailing_newline=True,
       )

Templates are loaded from ``adidt/templates/xsa/``.  The environment uses no
auto-escaping (DTS is not HTML) and preserves trailing newlines so that
rendered nodes concatenate cleanly.

Template rendering
~~~~~~~~~~~~~~~~~~

All template rendering goes through a single helper:

.. code-block:: python

   def _render(self, template_name: str, ctx: dict) -> str:
       return self._env.get_template(template_name).render(ctx)

``ctx`` is passed as a **positional dict**, not as keyword arguments.  This is
intentional: the context dict schema is documented in the context-builder
docstring (see below), and passing it positionally keeps the call sites
uniform.

SPI bus wrapping
~~~~~~~~~~~~~~~~

Multiple templates produce device nodes that must appear inside an
``&spi_bus { ... }`` overlay block.  The helper ``_wrap_spi_bus`` is used
instead of repeating the framing in each caller:

.. code-block:: python

   def _wrap_spi_bus(self, label: str, children: str) -> str:
       return (
           f"\t&{label} {{\n"
           '\t\tstatus = "okay";\n'
           "\t\t#address-cells = <1>;\n"
           "\t\t#size-cells = <0>;\n"
           f"{children}"
           "\t};"
       )

Templates
---------

Template files live in ``adidt/templates/xsa/`` and use the ``.tmpl``
extension.  Each template renders a single DTS node or a pair of related nodes
(e.g. a device node that must appear inside an SPI bus block).

How templates compose into a full device tree
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A complete merged DTS is assembled in layers.  The base DTS (from sdtgen)
provides the FPGA bus structure and CPU nodes.  ``NodeBuilder`` renders
individual templates, then the board builder and merger nest them into
the final tree.

The following diagram shows this layering for an FMCDAQ2 design (AD9523-1
clock + AD9680 ADC + AD9144 DAC).  The same pattern applies to all board
families — only the specific templates change.

.. code-block:: text

   ┌─────────────────────────────────────────────────────────────────────┐
   │  Merged DTS (.dts)                                                 │
   │                                                                    │
   │  /dts-v1/;                                                         │
   │  / {                                                               │
   │    amba: axi {   ◄── from base DTS (sdtgen)                        │
   │                                                                    │
   │  ┌───────────────────────────────────────────────────────────────┐  │
   │  │  /* --- Clock Generators --- */                               │  │
   │  │  axi_clkgen_0: ... { ... };  ◄── clkgen.tmpl                 │  │
   │  └───────────────────────────────────────────────────────────────┘  │
   │                                                                    │
   │  ┌───────────────────────────────────────────────────────────────┐  │
   │  │  /* --- JESD204 RX --- */                                     │  │
   │  │  axi_jesd204_rx_0: ... { ... };  ◄── jesd204_fsm.tmpl        │  │
   │  │                                        (generic path)         │  │
   │  └───────────────────────────────────────────────────────────────┘  │
   │                                                                    │
   │  ┌───────────────────────────────────────────────────────────────┐  │
   │  │  /* --- JESD204 TX --- */                                     │  │
   │  │  axi_jesd204_tx_0: ... { ... };  ◄── jesd204_fsm.tmpl        │  │
   │  └───────────────────────────────────────────────────────────────┘  │
   │                                                                    │
   │  ┌───────────────────────────────────────────────────────────────┐  │
   │  │  /* --- ADC / DAC / Transceiver PHY --- */                    │  │
   │  │  (board builder output — all nodes below)                     │  │
   │  │                                                               │  │
   │  │  ┌─────────────────────────────────────────────────────────┐  │  │
   │  │  │  &spi0 {  ◄── _wrap_spi_bus()                          │  │  │
   │  │  │    ┌────────────────────────────────────────────────┐   │  │  │
   │  │  │    │  clk0_ad9523: ad9523-1@0 { ... };             │   │  │  │
   │  │  │    │    ◄── ad9523_1.tmpl                           │   │  │  │
   │  │  │    ├────────────────────────────────────────────────┤   │  │  │
   │  │  │    │  adc0_ad9680: ad9680@2 { ... };               │   │  │  │
   │  │  │    │    ◄── ad9680.tmpl                             │   │  │  │
   │  │  │    ├────────────────────────────────────────────────┤   │  │  │
   │  │  │    │  dac0_ad9144: ad9144@1 { ... };               │   │  │  │
   │  │  │    │    ◄── ad9144.tmpl                             │   │  │  │
   │  │  │    └────────────────────────────────────────────────┘   │  │  │
   │  │  │  };                                                    │  │  │
   │  │  └─────────────────────────────────────────────────────────┘  │  │
   │  │                                                               │  │
   │  │  &axi_ad9680_dma { ... };      ◄── inline DMA overlay        │  │
   │  │  &axi_ad9144_dma { ... };      ◄── inline DMA overlay        │  │
   │  │                                                               │  │
   │  │  ┌─────────────────────────────────────────────────────────┐  │  │
   │  │  │  &axi_ad9680_core { ... };  ◄── tpl_core.tmpl (rx)     │  │  │
   │  │  │  &axi_ad9144_core { ... };  ◄── tpl_core.tmpl (tx)     │  │  │
   │  │  └─────────────────────────────────────────────────────────┘  │  │
   │  │                                                               │  │
   │  │  ┌─────────────────────────────────────────────────────────┐  │  │
   │  │  │  &axi_ad9680_jesd204_rx { ... };                        │  │  │
   │  │  │    ◄── jesd204_overlay.tmpl (rx)                        │  │  │
   │  │  │  &axi_ad9144_jesd204_tx { ... };                        │  │  │
   │  │  │    ◄── jesd204_overlay.tmpl (tx)                        │  │  │
   │  │  └─────────────────────────────────────────────────────────┘  │  │
   │  │                                                               │  │
   │  │  ┌─────────────────────────────────────────────────────────┐  │  │
   │  │  │  &axi_ad9680_adxcvr { ... };  ◄── adxcvr.tmpl (rx)     │  │  │
   │  │  │  &axi_ad9144_adxcvr { ... };  ◄── adxcvr.tmpl (tx)     │  │  │
   │  │  └─────────────────────────────────────────────────────────┘  │  │
   │  │                                                               │  │
   │  └───────────────────────────────────────────────────────────────┘  │
   │                                                                    │
   │    };  /* amba */                                                   │
   │  };    /* / */                                                      │
   └─────────────────────────────────────────────────────────────────────┘

**Key points:**

- The **base DTS** (from sdtgen) defines the root ``/`` and bus
  ``amba: axi`` nodes.  The merger inserts generated nodes inside the bus.
- **Generic nodes** (clkgens, JESD204 RX/TX) are rendered directly by
  ``NodeBuilder`` using ``clkgen.tmpl`` and ``jesd204_fsm.tmpl``.  These
  go into the ``clkgens``, ``jesd204_rx``, and ``jesd204_tx`` result
  lists.
- **Board builder nodes** go into the ``converters`` list.  A board
  builder (e.g. ``FMCDAQ2Builder``) calls ``_render()`` for each chip
  template, then ``_wrap_spi_bus()`` to nest the SPI device nodes
  inside an ``&spi0 { ... }`` overlay block.
- **Overlay nodes** (prefixed with ``&``) like ``&axi_ad9680_core``,
  ``&axi_ad9680_jesd204_rx``, and ``&axi_ad9680_adxcvr`` add properties
  to IP instances that sdtgen already defined in the base DTS.  The
  merger places these at the top level of the output.
- The ``DtsMerger`` arranges all nodes into the final DTS with section
  comments (``/* --- Clock Generators --- */``, etc.) and handles
  overlay-vs-bus placement.

The AD9084 variant is more complex (four JESD links, two SPI buses, HSCI,
ADF4382 PLL) but follows the same layering principle — each template renders
one DTS node, ``_wrap_spi_bus()`` groups SPI children, and the merger
assembles everything into the tree.

Indentation convention
~~~~~~~~~~~~~~~~~~~~~~

Templates use **tabs** for DTS indentation.  DTS nodes rendered at the top
level of an overlay (``&label { ... };``) start at the first column; content
inside them is indented one level per nesting depth.

Jinja2 delimiters are placed at the start of control lines with no leading
whitespace; rendered property lines carry their full DTS indentation inside the
string literal.

.. code-block:: jinja

   &{{ label }} {
   	compatible = "adi,axi-jesd204-rx-1.0";
   	clocks = {{ clocks_str }};
   {%- if clock_output_name %}
   	clock-output-names = "{{ clock_output_name }}";
   {%- endif %}
   	jesd204-device;
   };

The ``{%-`` trim marker removes the newline before the block tag, keeping
properties flush with no blank lines.

Pre-formatted string variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Jinja2 environment does not load the ``tojson`` filter.  Wherever a
property value is a list of quoted strings (e.g. ``clock-output-names`` or
``clock-names``), the context builder pre-formats it as a single string:

.. code-block:: python

   # In the context builder:
   clock_output_names_str = ", ".join(f'"{n}"' for n in names)

   # In the template:
   clock-output-names = {{ clock_output_names_str }};

This pattern appears in every template that emits multi-value string
properties.

Conditional properties
~~~~~~~~~~~~~~~~~~~~~~

Properties that are only present on some variants of a node use
``{%- if x is not none %}`` guards:

.. code-block:: jinja

   {%- if converter_resolution is not none %}
   	adi,converter-resolution = <{{ converter_resolution }}>;
   {%- endif %}

Use ``is not none`` (not a truthiness check) so that the property is emitted
when the value is ``0``.

``raw_channels`` escape hatch
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``hmc7044.tmpl`` supports two channel-rendering modes:

1. **Structured**: pass ``channels`` as a list of dicts with keys
   ``id``, ``name``, ``divider``, ``freq_str``, ``driver_mode``, etc.
   The template loops over the list and renders each channel sub-node.
2. **Raw string**: pass ``channels=None`` and ``raw_channels`` as a
   pre-rendered DTS string.  The template emits the string verbatim.

The raw-string path is used by the FMComms8 builder where the channel
block is too complex (or too hardware-specific) to be captured as structured
channel dicts without a dedicated schema extension.

Template catalogue
~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Template
     - Renders
   * - ``hmc7044.tmpl``
     - HMC7044 clock chip node (inside SPI bus).  Supports structured
       channels or raw ``raw_channels`` string.  All optional properties
       are guarded with ``is not none``.
   * - ``ad9523_1.tmpl``
     - AD9523-1 clock chip (FMCDAQ2); 8 channels hardcoded, optional GPIO
       lines (sync, status0/1).
   * - ``ad9528.tmpl``
     - AD9528 clock chip (FMCDAQ3); channels carry ``signal_source`` and
       ``is_sysref`` fields.
   * - ``ad9528_1.tmpl``
     - AD9528-1 variant (ADRV9009 standard path); ADRV9009-specific PLL
       properties, ``adi,driver-mode = <0>`` per channel.
   * - ``ad9680.tmpl``
     - AD9680 ADC.  ``use_spi_3wire`` flag controls ``spi-cpol``/
       ``spi-cpha`` and sysref-related properties.
   * - ``ad9144.tmpl``
     - AD9144 DAC.  ``jesd204-inputs`` offset is always 1.
   * - ``ad9152.tmpl``
     - AD9152 DAC (FMCDAQ3).  Includes ``spi-cpol``/``spi-cpha`` and
       ``adi,jesd-link-mode``.
   * - ``ad9172.tmpl``
     - AD9172 DAC.  Simple structure, mostly hardcoded properties.
   * - ``adxcvr.tmpl``
     - GT transceiver overlay.  ``use_div40=True`` emits two-clock (conv +
       div40) variant; ``use_div40=False`` emits single-clock variant.
       ``use_lpm_enable`` adds ``adi,use-lpm-enable``.
   * - ``jesd204_overlay.tmpl``
     - JESD204 controller overlay (RX or TX).  TX fields
       (``converter_resolution``, ``bits_per_sample``, etc.) are guarded
       with ``is not none``.  ``clock_output_name=None`` suppresses
       ``clock-output-names``.
   * - ``tpl_core.tmpl``
     - AXI TPL core overlay.  ``dma_label`` controls the DMA link;
       ``sampl_clk_ref`` adds a ``clocks`` property; ``pl_fifo_enable``
       adds ``adi,axi-pl-fifo-enable``.
   * - ``ad9084.tmpl``
     - AD9084 converter SPI device node.  Supports ``adi,device-profile-fw-name``
       for firmware loading, ``adi,axi-hsci-connected`` for HSCI linkup,
       ``dev_clk-clock-scales``, JESD204 lane mappings (``jrx0``/``jtx0``/
       ``jrx1``/``jtx1``), subclass, and ``adi,side-b-use-seperate-tpl-en``
       for dual-link designs.
   * - ``ad9081_mxfe.tmpl``
     - AD9081 MXFE device node.  Complex nested ``adi,tx-dacs`` and
       ``adi,rx-adcs`` sub-trees rendered from structured context.
   * - ``adrv9009.tmpl``
     - ADRV9009/9025 PHY device node.  ``{% if is_fmcomms8 %}`` block
       emits second PHY for dual-chip FMComms8 layouts.
   * - ``clkgen.tmpl``
     - AXI clock-generator overlay.
   * - ``jesd204_fsm.tmpl``
     - Generic JESD204 FSM overlay (used by the generic path).
   * - ``axi_ad9081.tmpl``
     - AXI AD9081 MXFE PL core overlay.

Context builders
----------------

Every template has a matching **context builder** method on ``NodeBuilder``.
Context builders are responsible for:

1. Reading values from the typed config struct (``_FMCDAQ2Cfg``,
   ``_AD9172Cfg``, etc.) or from the raw ``board_cfg`` dict.
2. Computing derived values (e.g. ``_fmt_hz()`` for frequency annotations,
   ``_fmt_gpi_gpo()`` for hex GPIO control strings).
3. Pre-formatting list values into strings (``clock_output_names_str``, etc.).
4. Returning a flat ``dict`` whose keys match the variable names used in the
   template.

Naming convention: ``_build_<chip>_ctx()`` or ``_build_<chip>_device_ctx()``.

Context builder docstrings document the full **context schema** — the
complete set of keys returned and the meaning of each.  For example:

.. code-block:: python

   def _build_jesd204_overlay_ctx(
       self,
       label: str,
       ps_clk_label: str,
       ps_clk_index: int,
       device_clk_ref: str,
       xcvr_label: str,
       jesd_link_id: int,
       is_tx: bool,
       octets_per_frame: int,
       frames_per_multiframe: int,
       num_converters: int | None = None,
       converter_resolution: int | None = None,
       bits_per_sample: int | None = None,
       control_bits_per_sample: int | None = None,
       clock_output_name: str | None = None,
   ) -> dict:
       """Build context dict for jesd204_overlay.tmpl.

       Context schema:
           label (str): DTS label (e.g. ``"axi_ad9680_jesd_rx_axi"``).
           direction (str): ``"rx"`` or ``"tx"``.
           clocks_str (str): Pre-formatted ``clocks = <...>`` value.
           clock_names_str (str): Pre-formatted ``clock-names = "..."`` value.
           clock_output_name (str | None): If set, emits ``clock-output-names``.
           f (int): Octets per frame.
           k (int): Frames per multiframe.
           converter_resolution (int | None): Emits ``adi,converter-resolution`` when set.
           ...
       """

Board-specific config structs
-------------------------------

Each board family has a private dataclass (``_FMCDAQ2Cfg``, ``_FMCDAQ3Cfg``,
``_AD9172Cfg``) that is populated from the runtime config by a
``_build_<family>_cfg()`` method.  These structs hold all resolved values for
one board so that context builders receive typed inputs instead of raw dicts.

The ADRV9009 and AD9081 builders work directly from the raw ``board_cfg``
dict (``cfg.get("adrv9009_board", {})``) because their configuration space is
larger and more variable.

Adding a new component
-----------------------

This section walks through the full process of adding DTS support for a new
SPI-attached chip — for example a new ADC called ``AD_NEW``.

Step 1 — Write the template
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create ``adidt/templates/xsa/ad_new.tmpl``.  Follow the indentation
convention (tabs, single-level inside the SPI bus node):

.. code-block:: jinja

   		{{ label }}: ad_new@{{ cs }} {
   			compatible = "adi,ad-new";
   			reg = <{{ cs }}>;
   			spi-max-frequency = <{{ spi_max_hz }}>;
   {%- if reset_gpio is not none %}
   			reset-gpios = <&{{ gpio_controller }} {{ reset_gpio }} 0>;
   {%- endif %}
   			adi,sampling-frequency = <{{ sampling_freq_hz }}>;
   			#clock-cells = <0>;
   		};

Rules:
- Use ``{%- if x is not none %}`` (not truthiness) for optional properties.
- Pre-format any multi-value string property in the context builder, not in
  the template.
- Keep the closing ``};`` at the same indentation as the opening ``label:``.

Step 2 — Write the context builder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Add a ``_build_ad_new_ctx()`` method to ``NodeBuilder``.  Document the full
context schema in the docstring:

.. code-block:: python

   def _build_ad_new_ctx(
       self,
       cs: int,
       spi_max_hz: int,
       gpio_controller: str,
       reset_gpio: int | None,
       sampling_freq_hz: int,
   ) -> dict:
       """Build context dict for ad_new.tmpl.

       Context schema:
           label (str): Always ``"adc0_ad_new"``.
           cs (int): SPI chip-select index.
           spi_max_hz (int): Maximum SPI frequency in Hz.
           gpio_controller (str): GPIO controller DTS label.
           reset_gpio (int | None): Reset GPIO line; ``None`` suppresses the property.
           sampling_freq_hz (int): Sampling frequency in Hz.
       """
       return {
           "label": "adc0_ad_new",
           "cs": cs,
           "spi_max_hz": spi_max_hz,
           "gpio_controller": gpio_controller,
           "reset_gpio": reset_gpio,
           "sampling_freq_hz": sampling_freq_hz,
       }

Step 3 — Write tests
~~~~~~~~~~~~~~~~~~~~

Add tests to ``test/xsa/test_node_builder_templates.py``.  Follow TDD: write
the test first, confirm it fails, then implement.

.. code-block:: python

   def test_ad_new_template_renders():
       ctx = {
           "label": "adc0_ad_new",
           "cs": 0,
           "spi_max_hz": 10_000_000,
           "gpio_controller": "gpio",
           "reset_gpio": 100,
           "sampling_freq_hz": 245_760_000,
       }
       out = NodeBuilder()._render("ad_new.tmpl", ctx)
       assert 'compatible = "adi,ad-new"' in out
       assert "adc0_ad_new: ad_new@0" in out
       assert "reset-gpios = <&gpio 100 0>" in out
       assert "adi,sampling-frequency = <245760000>" in out

   def test_ad_new_context_builder():
       ctx = NodeBuilder()._build_ad_new_ctx(
           cs=0,
           spi_max_hz=10_000_000,
           gpio_controller="gpio",
           reset_gpio=100,
           sampling_freq_hz=245_760_000,
       )
       assert ctx["label"] == "adc0_ad_new"
       assert ctx["reset_gpio"] == 100

Run tests:

.. code-block:: bash

   nox -s tests -- test/xsa/test_node_builder_templates.py -v -k "ad_new"

Step 4 — Add board detection (if needed)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the new chip is the primary converter in a design, add a detection method
to ``XsaTopology`` in ``topology.py``:

.. code-block:: python

   def is_ad_new_design(self) -> bool:
       """Return True if the topology contains an AD_NEW design."""
       return self.has_converter_types("axi_ad_new")

Or use JESD instance name matching if there is no dedicated AXI IP type:

.. code-block:: python

   def is_ad_new_design(self) -> bool:
       return "ad_new" in self._jesd_name_blob()

Add the family to ``inferred_converter_family()`` in the priority list.

Step 5 — Wire into a board builder or ``build()``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the chip slots into an existing board family, call ``_render()`` inside the
appropriate board builder and concatenate the result into ``spi_children``:

.. code-block:: python

   spi_children = (
       self._render("existing_clk.tmpl", clk_ctx)
       + self._render("ad_new.tmpl", self._build_ad_new_ctx(...))
   )
   nodes.append(self._wrap_spi_bus(spi_bus, spi_children))

If it is a new family entirely, create a new board builder method following
the existing pattern (see ``_build_fmcdaq2_nodes()`` as a reference), add a
topology check at the top that returns ``[]`` early, and call it from
``build()``.

Adding a new board
------------------

A **board** in this context means a specific combination of FPGA platform and
daughter card (e.g. ``ad_new_zcu102``).  Adding board support involves:

1. Creating a board JSON profile
2. Registering the profile
3. Adding topology detection (if the FPGA part is new)
4. Writing or extending a board builder

Step 1 — Create the board JSON profile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create ``adidt/xsa/profiles/ad_new_zcu102.json``.  A profile supplies default
values for all board-wiring keys so that users only need to override what
differs:

.. code-block:: json

   {
     "name": "ad_new_zcu102",
     "defaults": {
       "jesd": {
         "rx": { "F": 4, "K": 32 },
         "tx": { "F": 4, "K": 32 }
       },
       "ad_new_board": {
         "spi_bus": "spi0",
         "clk_cs": 0,
         "adc_cs": 1,
         "clk_spi_max_frequency": 10000000,
         "adc_spi_max_frequency": 10000000,
         "reset_gpio": 100,
         "sampling_freq_hz": 245760000
       }
     }
   }

Profile keys are validated against a schema in ``profiles.py``.  Add the new
board-level key (``"ad_new_board"`` in this example) to ``KNOWN_BOARD_KEYS``
in ``profiles.py`` and define its allowed sub-keys to prevent silent typos.

Step 2 — Register the profile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In ``profiles.py``, add an entry to the profile registry so that
``XsaPipeline`` can auto-select or explicitly load it:

.. code-block:: python

   _BUILTIN_PROFILES = [
       ...
       "ad_new_zcu102",
   ]

Auto-selection logic lives in ``XsaParser`` / ``XsaPipeline``.  If the new
design is unambiguously identifiable from the topology (e.g. a unique
``axi_ad_new`` IP type), add it to the auto-selection table.  If it shares
IP names with an existing family, require explicit ``profile=`` selection and
document this in the ``xsa.rst`` user guide.

Step 3 — Platform support
~~~~~~~~~~~~~~~~~~~~~~~~~~

If the FPGA part is not yet known, add it to ``_PART_TO_PLATFORM`` in
``topology.py``:

.. code-block:: python

   _PART_TO_PLATFORM = {
       ...
       "xczu9eg": "zcu102",
       "xc7z045": "zc706",
       "xcvu9p":  "vcu118",   # ← new entry
   }

``inferred_platform()`` uses this table to select PS clock labels and GPIO
controller names.  If a new platform needs different labels, update the
``_platform_ps_labels()`` helper in ``NodeBuilder``.

Step 4 — Board builder
~~~~~~~~~~~~~~~~~~~~~~~

Create ``_build_ad_new_nodes()`` on ``NodeBuilder`` following the pattern
below:

.. code-block:: python

   def _build_ad_new_nodes(
       self,
       topology: XsaTopology,
       cfg: dict[str, Any],
       ps_clk_label: str,
       ps_clk_index: int,
   ) -> list[str]:
       """Build DTS node strings for an AD_NEW design.

       Returns an empty list if the topology is not an AD_NEW design.
       """
       if not topology.is_ad_new_design():
           return []

       board_cfg = cfg.get("ad_new_board", {})
       spi_bus   = str(board_cfg.get("spi_bus", "spi0"))
       clk_cs    = int(board_cfg.get("clk_cs", 0))
       adc_cs    = int(board_cfg.get("adc_cs", 1))
       ...

       # Build and render each node
       clk_ctx = self._build_hmc7044_ctx(...)
       adc_ctx = self._build_ad_new_ctx(...)

       spi_children = (
           self._render("hmc7044.tmpl", clk_ctx)
           + self._render("ad_new.tmpl", adc_ctx)
       )

       nodes: list[str] = [
           # misc / DMA / XCVR / JESD overlay nodes ...
           self._wrap_spi_bus(spi_bus, spi_children),
       ]
       return nodes

Then call it from ``build()``:

.. code-block:: python

   result["converters"].extend(
       self._build_ad_new_nodes(topology, cfg, ps_clk_label, ps_clk_index)
   )

Regression and parity testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For hardware-verified designs, add a **parity test** that runs the full
pipeline against a reference DTS and checks that required roles are present:

.. code-block:: python

   # test/xsa/test_parity.py  (or equivalent)
   def test_ad_new_zcu102_parity(xsa_path, ref_dts_path):
       cfg = load_profile("ad_new_zcu102")
       result = XsaPipeline().run(
           xsa_path=xsa_path,
           cfg=cfg,
           output_dir=tmp_path,
           reference_dts=ref_dts_path,
           strict_parity=True,
       )
       # Passes when all required roles from the reference are present.

Unit tests for the new context builder and template should live in
``test/xsa/test_node_builder_templates.py``.

Utility helpers
---------------

Several static helpers on ``NodeBuilder`` are useful when writing new board
builders.

``_fmt_hz(hz)``
   Formats an integer frequency into a human-readable string:
   ``245760000 → "245.76 MHz"``.  Used for DTS comment annotations.

``_fmt_gpi_gpo(controls)``
   Formats a list of integer values as lowercase hex tokens for HMC7044
   GPI/GPO control properties: ``[0x1F, 0x2B] → "0x1f 0x2b"``.

``_topology_instance_names(topology)``
   Returns the union of all IP instance names from a topology, with hyphens
   replaced by underscores to match DTS label conventions.

``_pick_matching_label(topology_names, default, required_tokens)``
   Returns the first topology name containing all ``required_tokens`` (as
   substrings of the lowercased name), or ``default`` if none match.  Useful
   for finding labels like ``axi_adrv9009_rx_xcvr`` when the exact name varies
   by design.

``_wrap_spi_bus(label, children)``
   Wraps a string of rendered device-node content inside an
   ``&label { status = "okay"; ... };`` SPI bus overlay block.

``_coerce_board_int(value, key_path)``
   Converts a config value to ``int``, raising ``ValueError`` with context
   when conversion fails (guards against ``True``/``False`` being accidentally
   passed where integers are expected).

Testing conventions
--------------------

All DTS-generation logic should be covered at three levels:

1. **Template smoke tests** (``test_node_builder_templates.py``): call
   ``NodeBuilder()._render(template, ctx)`` with a minimal hand-crafted
   context dict and assert that key properties and labels appear in the
   output.

2. **Context builder unit tests** (``test_node_builder_context_builders.py``):
   call ``NodeBuilder()._build_<x>_ctx(...)`` with specific inputs and assert
   the returned dict contains the expected values, especially for edge cases
   and derived fields.

3. **Board builder integration tests** (``test_node_builder.py``): call
   ``NodeBuilder().build(topology, cfg)`` with a mocked or minimal
   ``XsaTopology`` and assert that the returned node list contains the
   expected DTS fragments.

Follow TDD: write the failing test first, run it to confirm the failure, then
implement.

.. code-block:: bash

   # Run only the new tests while developing
   nox -s tests -- test/xsa/ -v -k "ad_new"

   # Run the full suite before committing
   nox -s tests -- test/xsa/ -v
