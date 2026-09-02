Authoring a new device class
============================

This guide teaches you how to add a new clock, converter, transceiver,
eval board, or FPGA-platform class to ``pyadi-dt``.  It follows the
declarative pipeline end-to-end and ends in three cookbook recipes you
can copy from.

If you only need to generate device trees for **boards that are already
supported**, you don't need this guide — see :doc:`../quickstart` or
:doc:`../xsa`.  If you are plugging the XSA pipeline into a **new
Vivado design family**, see :doc:`../xsa_developer` (board-builder
authoring); that work typically still reuses the device classes
introduced here.

1. Overview & scope
-------------------

The declarative device layer lives under ``adidt/devices/``.  Every
concrete device class — ``HMC7044``, ``AD9081``, ``ADRV9009``,
``ADF4382``, etc. — is a ``pydantic.BaseModel`` whose fields map 1:1
to DT properties.  Rendering is driven by
:func:`adidt.devices._dt_render.render_node`, which walks the model,
emits each field by its alias, and lets the class inject
phandle-valued or coupled lines through a small set of optional hooks.

This guide covers:

- The shape of a ``Device`` subclass (ClassVars, pydantic fields,
  field markers, optional hooks).
- How ``ports`` (SPI, clock outputs, GT lanes) connect a device to the
  rest of a :class:`adidt.System`.
- The two converter-shape patterns: MxFE (AD9081/AD9084 with separate
  ``.adc`` / ``.dac`` sides) vs. single-transducer (ADRV9009).
- Step-by-step recipes for adding a clock, a converter/transceiver, and
  an eval-board / FPGA-platform class.
- How the class you wrote integrates with the XSA pipeline.

2. Class hierarchy at a glance
------------------------------

::

   Device                             # pydantic BaseModel, base of everything
    │                                 # (adidt/devices/base.py)
    ├── ClockDevice                   # adds: spi: SpiPort, clk_out[N]
    │    ├── HMC7044
    │    ├── AD9523_1 / AD9528 / AD9528_1
    │    └── ADF4382
    ├── ConverterDevice               # adds: spi: SpiPort
    │    ├── AD9081         (MxFE)    #   has .adc / .dac (ConverterSide)
    │    ├── AD9084         (MxFE)
    │    ├── AD9172         (single-side DAC)
    │    └── AD9680         (single-side ADC)
    ├── ADRV9009                      # single-transducer RF transceiver
    │                                 # (also backs AD9371/ADRV9371)
    └── FpgaBoard                     # platform constants + ports
         ├── zcu102 / zc706
         ├── vcu118 / vpk180
         └── …

   Ports (non-pydantic helpers, adidt/devices/base.py):
     SpiPort        — secondary side on clock / converter devices
     SpiMaster      — primary side on FPGA (adidt/fpga/base.py)
     ClockOutput    — one of a clock device's output channels
     GtLane         — one FPGA GT transceiver lane

   Composition (one-level-up from devices):
     EvalBoard      — pre-wired clock + converter (adidt/eval/…)
     System         — user-facing orchestrator (adidt/system.py)

   Aggregate model + renderer (both the declarative API and the XSA
   pipeline funnel into here):
     BoardModel, ComponentModel, JesdLinkModel  (adidt/model/board_model.py)
     BoardModelRenderer                         (adidt/model/renderer.py)

   FPGA-IP overlays emitted alongside SPI peripherals:
     Adxcvr / Jesd204Overlay / TplCore          (adidt/devices/fpga_ip/)

3. End-to-end call flow
-----------------------

Trace one call, ``adidt.System(...).generate_dts()``, through the
stack:

**1. User assembly** — the user instantiates an :class:`EvalBoard`
and an :class:`FpgaBoard`, hands them to a :class:`System`, and calls
``connect_spi`` + ``add_link`` to record connections.  No DTS text
is produced yet; the ``System`` object just holds a list of
``_SpiConnection`` and ``_JesdLink`` records (see ``adidt/system.py``
for the dataclasses).

**2. BoardModel assembly** — ``System.to_board_model()`` iterates the
devices reachable through ``components`` (``_all_devices``), resolves
each device's SPI bus/CS from the recorded connections
(``_spi_location``), gathers System-level context (``_extra_ctx_for``,
which injects the FPGA's ``gpio_label`` and any clkgen references the
device needs), and calls the device's
:meth:`~adidt.devices.base.Device.to_component_model`.  For every
recorded JESD link ``_build_jesd_link`` constructs the JESD overlay,
ADXCVR overlay, and TPL core overlay into a
:class:`~adidt.model.board_model.JesdLinkModel`.  The result is a
:class:`~adidt.model.board_model.BoardModel` whose
:class:`~adidt.model.board_model.ComponentModel` entries each carry a
fully-rendered DT node string in their ``rendered`` field.

**3. Device rendering** — inside each device's ``render_dt`` the
engine is :func:`adidt.devices._dt_render.render_node`.  It:

- Emits the ClassVar header: ``compatible``, ``reg``, ``#*-cells`` and
  other keys from ``dt_header``, and boolean flags from ``dt_flags``.
- Walks pydantic fields with ``Field(alias="adi,…")`` and emits them
  by type (``int`` → ``<N>``, ``bool`` → bare flag, ``list[int]`` →
  space-separated cells, ``str`` → ``"…"``).
- Honours ``Annotated`` markers from :mod:`adidt.devices._fields` —
  ``DtSubnodes`` turns a ``dict[key, child]`` field into child nodes,
  ``DtSkip`` drops a field entirely, ``DtBits64`` emits the value as
  ``/bits/ 64 <N>`` for gigahertz-scale frequencies.
- Calls the device's ``extra_dt_lines(context)`` for coupled or
  phandle-valued properties (``clocks`` + ``clock-names``, GPIO
  phandles, and similar lines that depend on System-supplied labels).
- Calls ``trailing_blocks(context)`` for large nested blocks
  (AD9081's ``adi,tx-dacs { … }`` / ``adi,rx-adcs { … }`` live here).

**4. Aggregate rendering** — ``System.generate_dts()`` calls
:class:`~adidt.model.renderer.BoardModelRenderer`, which groups
ComponentModels by SPI bus, wraps each group in ``&spi_bus { … };``,
then appends the ``jesd_overlay_rendered`` / ``xcvr_rendered`` /
``tpl_core_rendered`` strings as sibling overlays, plus any DMA
``&<dma_label>`` overlays derived from the JESD links.  The output
is a single DTS overlay string.

That's the whole pipeline — four layers (user, System, device,
renderer) and no templates.

4. Anatomy of a Device
----------------------

Most devices can be written by sub-classing a convenience base
(:class:`~adidt.devices.clocks.ClockDevice`,
:class:`~adidt.devices.converters.ConverterDevice`) and filling in
four pieces: **ClassVars**, **pydantic fields**, optional
**``extra_dt_lines``**, and optional **``trailing_blocks``**.

**ClassVars** (declared once per subclass, never per-instance):

- ``part`` — short identifier (e.g. ``"hmc7044"``, ``"ad9081"``) that
  ends up in :class:`~adidt.model.board_model.ComponentModel.part`.
- ``role`` — ``"clock"`` / ``"converter"`` / ``"transceiver"`` /
  ``"fpga"``; drives :class:`~adidt.model.board_model.ComponentModel.role`.
- ``label`` (instance field, not ClassVar) — the DT label used for
  phandles.  Always overridable at construction time.
- ``compatible`` / ``dt_header`` / ``dt_flags`` — consumed by
  :func:`render_node`.  ``dt_header`` is an ordered dict of non-field
  properties that always appear (``#clock-cells``, ``#jesd204-cells``,
  ``clock-output-names`` when static, etc.).  ``dt_flags`` is a tuple of
  bare property names (``jesd204-device``, ``jesd204-sysref-provider``).
- ``template`` — legacy Jinja2 template name.  For fully declarative
  devices this is the empty string.

**Pydantic fields** with DT-alias names:

.. code-block:: python

   class HMC7044(ClockDevice):
       compatible: ClassVar[str] = "adi,hmc7044"
       dt_header: ClassVar[dict] = {"#clock-cells": 1, "#jesd204-cells": 2}
       dt_flags: ClassVar[tuple] = ("jesd204-device",)

       vcxo_hz: int = Field(..., alias="adi,vcxo-frequency")
       pll2_output_hz: int = Field(..., alias="adi,pll2-output-frequency")
       pll1_ref_autorevert: bool = Field(False, alias="adi,pll1-ref-autorevert-enable")

Fields without an alias are skipped unless annotated (see below).

**Field markers** (from :mod:`adidt.devices._fields`) attach via
``typing.Annotated``:

- ``Annotated[dict[int, ClockChannel], DtSubnodes(node_name="channel",
  label_template="{parent}_c{key}")]`` — renders each dict entry as
  ``channel@<key> { … };`` under the parent, with the emitted label
  coming from ``label_template``.
- ``Annotated[str, DtSkip()]`` — Python-only state (ports, pre-joined
  strings consumed by ``extra_dt_lines``, etc.).
- ``Annotated[int, DtBits64()]`` — emit ``/bits/ 64 <value>`` so
  gigahertz-scale frequencies fit in 64-bit DT cells.

**Optional hooks** on the class:

- ``extra_dt_lines(context: dict | None = None) -> list[str]`` —
  returns raw DT property lines for values the field-walk can't
  produce.  Used for phandles (``clocks = <&hmc7044 2>;``), coupled
  pairs (``clocks`` + ``clock-names``), and anything that needs
  ``context["gpio_label"]`` or other System-injected values.
  See :class:`adidt.devices.clocks.HMC7044.extra_dt_lines` and
  :class:`adidt.devices.transceivers.ADRV9009.extra_dt_lines`.
- ``trailing_blocks(context: dict | None = None) -> list[str]`` —
  returns big nested-block strings that get spliced between the last
  rendered field and the closing ``};``.  AD9081's
  ``adi,tx-dacs`` / ``adi,rx-adcs`` nests live here.
- ``render_dt(cs, context)`` — only override if you need to bypass
  ``render_node`` entirely (e.g. ADRV9009's per-instance ``reg = <cs>;``
  and variable node-name).  Most devices inherit the default.
- ``build_context(cs, extra)`` — hook for legacy Jinja2 template
  glue; declarative devices almost never override it.

Reference example — the canonical full-featured device —
``adidt/devices/clocks/hmc7044.py``.

5. Port & clock-output plumbing
-------------------------------

``pyadi-dt`` separates **what the device is** (the pydantic model)
from **where it's wired** (the ``Port`` objects).  A ``Device`` never
mutates another device; connections live entirely in the
:class:`~adidt.system.System` instance.

- :class:`adidt.devices.base.SpiPort` is attached to clock and
  converter devices by their convenience base classes in their
  ``model_post_init``.  It is the object the user passes to
  ``System.connect_spi(secondary=…)``.
- :class:`adidt.fpga.SpiMaster` is the primary side, built from the
  FPGA platform's ``SPI_LABELS`` tuple inside
  :meth:`adidt.fpga.FpgaBoard.model_post_init`.
- :class:`adidt.devices.base.ClockOutput` represents one output channel
  on a clock device.  Its ``index`` is the hardware channel number,
  ``name`` is an optional board-level alias (``"DEV_REFCLK"``,
  ``"FPGA_SYSREF"``), and ``is_sysref`` marks it as a SYSREF line for
  the JESD204 fabric.  ``EvalBoard`` subclasses assign named aliases
  so the user can write ``fmc.dev_refclk`` instead of
  ``fmc.clock.clk_out[2]``; see
  ``adidt/eval/ad9081_fmc.py:_CLOCK_CHANNEL_MAP``.
- :class:`adidt.devices.base.GtLane` is built per FPGA from
  ``NUM_GT_LANES``; the user passes ``fpga.gt[N]`` as the JESD data
  endpoint for :meth:`adidt.system.System.add_link`.

How the System resolves a device's bus/CS: ``_spi_location(device)``
in ``adidt/system.py`` walks the recorded ``_SpiConnection`` list,
matches the device to either end, and returns
``(bus_label_from_SpiMaster.label, cs)``.  If you add a new device
category you don't need to change this — just make sure your class
exposes its ``SpiPort`` the same way ``ClockDevice`` and
``ConverterDevice`` do.

6. Converter patterns
---------------------

Two shapes, chosen by whether the chip has logically independent JESD
transmit / receive paths.

**MxFE — separate sides.**  :class:`~adidt.devices.converters.AD9081`
and :class:`~adidt.devices.converters.AD9084` each expose ``.adc`` and
``.dac`` attributes that are
:class:`~adidt.devices.converters.base.ConverterSide` models carrying
their own :class:`~adidt.devices.converters.base.Jesd204Settings`.
Each side has a ``MODE_TABLE`` — a mapping from
``(link_mode, jesd_class)`` to ``(F, K, M, L, Np, S)`` — that
``ConverterSide.set_jesd204_mode`` uses to look up and stamp the JESD
framing parameters.  :meth:`adidt.system.System.add_link` reads
``source.jesd204_settings`` (or ``sink.jesd204_settings``) when
building the link, so the System path is "set mode on the side, then
wire with ``add_link``".

**Single-transducer.**
:class:`~adidt.devices.transceivers.ADRV9009` (which also backs
AD9371 / ADRV9371 — see the device's own class docstring) has a single
``jesd204_settings`` on the converter itself; there's no ``.adc`` /
``.dac`` split.  :meth:`adidt.system.System._build_jesd_link` branches
on ``hasattr(converter, "adc")``, so the System API accepts either
shape transparently.

**Single-side DAC or ADC.**
:class:`~adidt.devices.converters.AD9172` /
:class:`~adidt.devices.converters.AD9680` are simpler still — one set
of JESD settings, one SPI port, no sub-models.  Copy these for a new
single-side part.

The pattern to pick for a new device = "what the silicon physically
looks like".  If the datasheet has independent TX and RX link
configurations, use the MxFE shape; otherwise use the single-
transducer or single-side shape.

7. Cookbook 1 — Adding a new clock device
-----------------------------------------

Template: ``adidt/devices/clocks/hmc7044.py`` (full-featured) or
``adidt/devices/clocks/adf4382.py`` (minimal, no sub-nodes).

**a.** Create ``adidt/devices/clocks/my_clock.py`` and start from:

.. code-block:: python

   from __future__ import annotations
   from typing import Annotated, ClassVar
   from pydantic import Field
   from .._dt_render import render_node
   from .._fields import DtSkip
   from .base import ClockDevice

   class MY_CLOCK(ClockDevice):
       part: ClassVar[str] = "my_clock"
       compatible: ClassVar[str] = "adi,my-clock"
       dt_header: ClassVar[dict] = {"#clock-cells": 1}
       dt_flags: ClassVar[tuple] = ()

       label: str = "my_clock"
       spi_max_hz: int = Field(10_000_000, alias="spi-max-frequency")
       vcxo_hz: int = Field(..., alias="adi,vcxo-frequency")
       # …one pydantic field per DT property…

**b.** If your chip has N output channels exposed as sub-nodes, add a
``ChannelModel`` sub-class (see ``ClockChannel`` in
``adidt/devices/clocks/base.py``) and declare:

.. code-block:: python

   from .._fields import DtSubnodes

   channels: Annotated[
       dict[int, MyChannel],
       DtSubnodes(node_name="channel", label_template="{parent}_c{key}"),
   ] = Field(default_factory=dict)

**c.** Override ``extra_dt_lines`` if any of your DT properties are
coupled (``clocks`` + ``clock-names``) or need a System-injected
phandle.  Mirror the pattern in :class:`HMC7044.extra_dt_lines`.

**d.** Register the class for public import:

- Add the import to ``adidt/devices/clocks/__init__.py``.
- If your chip needs a named clock-output alias on eval boards, have
  the eval board's ``_CLOCK_CHANNEL_MAP`` populate it (see
  ``adidt/eval/ad9081_fmc.py``).

**e.** Unit-test the render path.  Copy ``test/devices/test_hmc7044.py``
as a template — it instantiates the device, calls ``render_dt(cs=0)``,
and asserts on the emitted DT string.  The same tests also round-trip
through :class:`~adidt.model.board_model.ComponentModel` (the
``rendered`` field is what the renderer consumes).

8. Cookbook 2 — Adding a new converter / transceiver
----------------------------------------------------

Decide first which shape your silicon wants:

- **MxFE**: start from ``adidt/devices/converters/ad9081.py``
  (quad-ADC + quad-DAC with ``.adc`` / ``.dac`` sides).
- **Single-transducer RF**: start from
  ``adidt/devices/transceivers/adrv9009.py``.
- **Single-side DAC or ADC**: start from
  ``adidt/devices/converters/ad9172.py`` or
  ``adidt/devices/converters/ad9680.py``.

**a.** For a new MxFE, define your Adc/Dac sub-classes with a
``MODE_TABLE``:

.. code-block:: python

   _MY_RX_MODE_TABLE = {
       (9, "jesd204b"): {"M": 8, "L": 4, "F": 4, "K": 32, "Np": 16, "S": 1},
       # …one entry per supported (link_mode, jesd_class) combination…
   }

The System API's :meth:`ConverterSide.set_jesd204_mode` consults this
table to stamp ``F``/``K``/``M``/``L``/``Np``/``S`` on
``jesd204_settings``.  Missing modes raise a clear error at config
time rather than mis-rendering DT.

**b.** For the parent device, inherit :class:`ConverterDevice`, expose
``adc`` and ``dac`` sub-models, and — if any DT properties are coupled
or phandle-valued — override ``extra_dt_lines`` and/or
``trailing_blocks``.  AD9081 is the reference for a complex layout
(separate ``adi,tx-dacs`` and ``adi,rx-adcs`` nested blocks, per-DAC
``adi,crossbar-select`` values, per-channel ``adi,gain``).

**c.** When wiring with :class:`adidt.System`, users pass
``fmc.converter.adc`` as the ``source`` of an RX ``add_link`` call and
``fmc.converter.dac`` as the ``sink`` of a TX call.  For single-
transducer devices, they pass ``fmc.converter`` directly; the System
API's ``_build_jesd_link`` branches on ``hasattr(converter, "adc")``
and treats the bare converter as the side in that case (see
``adidt/system.py``).

**d.** Register in ``adidt/devices/converters/__init__.py`` (or
``adidt/devices/transceivers/__init__.py``) so user imports work, then
unit-test by mirroring
``test/devices/test_ad9084_vpk180.py`` or
``test/devices/test_system_adrv937x_zc706.py``.

9. Cookbook 3 — Adding an eval board or an FPGA board
-----------------------------------------------------

**Eval board.**  An :class:`~adidt.eval.EvalBoard` subclass pre-wires
a clock IC and a converter with the schematic-level decisions (which
HMC7044 channel is DEV_REFCLK, which GPIO pin holds the converter in
reset, etc.) so users don't have to know them.

Start from ``adidt/eval/ad9081_fmc.py`` for the full pattern or
``adidt/eval/adrv937x_fmc.py`` for a compact one:

1. Define ``_CLOCK_CHANNEL_MAP`` — a dict of ``{index: {name, divider,
   is_sysref}}`` entries enumerating the named clock outputs.
2. In ``__init__``, construct the clock device with those channels and
   the converter device with its board-level GPIOs.
3. Add ``@property`` aliases that return the named ``ClockOutput`` for
   each downstream signal (``dev_refclk``, ``dev_sysref``,
   ``fpga_sysref``, ``core_clk_rx``, …).

:meth:`EvalBoard.devices` yields any attribute that is a
:class:`~adidt.devices.base.Device`, which is how
``System._all_devices`` discovers your clock + converter — no
registration needed.

**FPGA board.**  An :class:`~adidt.fpga.FpgaBoard` subclass is purely
a declaration of platform constants.  Start from
``adidt/fpga/zcu102.py`` (Zynq UltraScale+) or
``adidt/fpga/zc706.py`` (Zynq-7000) and set:

- ``PLATFORM`` — short platform name used in manifests
  (``"zcu102"``, ``"zc706"``, ``"vcu118"``, …).
- ``ADDR_CELLS`` — ``1`` on 32-bit AXI platforms (Zynq-7000,
  MicroBlaze), ``2`` on 64-bit (Zynq UltraScale+, Versal).
- ``PS_CLK_LABEL`` / ``PS_CLK_INDEX`` — the label and index passed to
  ``<&<label> <index>>`` in phandles, e.g. ``<&zynqmp_clk 71>``.
- ``GPIO_LABEL`` — the DT label of the GPIO controller (``"gpio"`` on
  ZynqMP, ``"gpio0"`` on Zynq-7000).
- ``SPI_LABELS`` — the tuple of primary SPI-master labels in bus-index
  order.  ``FpgaBoard.model_post_init`` builds one ``SpiMaster`` per
  entry and exposes them as ``fpga.spi[i]``.
- ``NUM_GT_LANES`` — number of GT transceiver lanes; ``model_post_init``
  populates ``fpga.gt[0…N-1]``.
- ``JESD_PHY`` / ``DEFAULT_FPGA_ADC_PLL`` / ``DEFAULT_FPGA_DAC_PLL`` —
  platform defaults that feed the JESD204 overlay rendering via
  :mod:`adidt._naming`.

Export the new class from ``adidt/fpga/__init__.py`` so users can do
``adidt.fpga.my_board()``.

10. Bridging to the XSA pipeline
--------------------------------

Every device class written against the declarative layer is
automatically usable from the XSA pipeline.  An ``XsaBuilder`` (e.g.
:class:`adidt.xsa.build.builders.adrv937x.ADRV937xBuilder`) parses the
topology extracted from a Vivado ``.xsa`` archive, constructs the
same Pydantic device models you wrote, and feeds them into the same
:class:`~adidt.model.renderer.BoardModelRenderer`.  The output path
converges — the only difference is who picked the configuration.

Compare the smallest builder side-by-side with its device class to
see the pattern:

- ``adidt/xsa/build/builders/adrv937x.py`` — builder side.
- ``adidt/devices/transceivers/adrv9009.py`` — device side (reused
  here because AD9371 silicon shares the DT layout).

For detailed XSA pipeline coverage — topology extraction, the
``BoardBuilder`` protocol, ``NodeBuilder`` orchestration, the DTS
merger — see :doc:`../xsa_developer`.  If you are writing a new
builder and not a new device, that's your starting point; the device
cookbook above remains the reference for any new devices your
builder needs to emit.

11. Testing your new device
---------------------------

Three layers of tests exercise progressively more of the stack:

- **Device unit tests.**  Instantiate the device, call ``render_dt``,
  assert on the emitted string.  Cheap and should cover every non-
  trivial field and every ``extra_dt_lines`` branch.  Pattern:
  ``test/devices/test_hmc7044.py`` (14 cases covering headers, field
  rendering, coupled-property lines, and sub-node emission).
- **System-API smoke tests.**  Build an :class:`EvalBoard` + an
  :class:`FpgaBoard`, wire them through :class:`adidt.System`, and
  call ``generate_dts()``.  Assert on the top-level structure
  (``&spi0 { … };`` wrappers, presence of the compatible string,
  JESD link directions).  Pattern:
  ``test/devices/test_system_ad9081_zcu102.py`` (also see
  ``test_system_adrv937x_zc706.py`` for the single-transducer
  shape).
- **XSA builder tests.**  If you added a builder, write a matching
  unit test with a synthetic topology fixture and a golden-file
  regression test.  Patterns:
  ``test/xsa/test_builders/test_adrv937x_builder.py`` and
  ``test/xsa/test_builders/test_golden_files.py``.  The golden-file
  test captures exact DTS output so unintentional changes surface in
  review.

When the device has real hardware on the coordinator, the
end-to-end hardware tests in ``test/hw/`` take over — see the
"End-to-end hardware verification" section of :doc:`../api/devices`
for the current test matrix and how to run it via the coordinator.
