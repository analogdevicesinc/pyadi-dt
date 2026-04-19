Declarative Devices
===================

The ``adidt.devices`` package is the single source of truth for how ADI
hardware maps to device-tree nodes.  Every modeled device is a small
pydantic class whose fields are the DT properties it emits — no Jinja2
templates, no intermediate context dicts.  A device's ``render_dt``
method returns the DTS text directly.

Design in three pieces
----------------------

**1. Typed fields with DT-property aliases.**  Each field on a
:class:`~adidt.devices.base.Device` subclass carries the exact DT
property name via ``Field(alias="adi,...")``.  The Python attribute is
the human-facing handle; the alias is the on-disk name.

.. code-block:: python

   class HMC7044(ClockDevice):
       compatible: ClassVar[str] = "adi,hmc7044"
       dt_header: ClassVar[dict] = {"#clock-cells": 1, "#jesd204-cells": 2}
       dt_flags: ClassVar[tuple] = ("jesd204-device",)

       vcxo_hz: int = Field(..., alias="adi,vcxo-frequency")
       pll2_output_hz: int = Field(..., alias="adi,pll2-output-frequency")
       pll1_ref_autorevert: bool = Field(False, alias="adi,pll1-ref-autorevert-enable")

The :mod:`adidt.devices._dt_render` renderer walks these fields,
formats each value by its Python type, and emits::

   adi,vcxo-frequency = <122880000>;
   adi,pll2-output-frequency = <2949120000>;
   adi,pll1-ref-autorevert-enable;

**2. Field markers for non-scalar cases.**  Fields that don't map 1:1
to a DT value use :mod:`adidt.devices._fields` markers, applied via
``typing.Annotated``:

- :class:`~adidt.devices._fields.DtSubnodes` — a ``dict[key, child]``
  renders as child DT nodes (e.g. HMC7044 channels).
- :class:`~adidt.devices._fields.DtSkip` — excludes a field from
  rendering (Python-only state, ports, etc.).
- :class:`~adidt.devices._fields.DtBits64` — emit ``/bits/ 64 <N>``
  for sampling/converter frequencies that don't fit in a 32-bit cell.

**3. An ``extra_dt_lines`` hook for coupled properties.**  Properties
that need System-supplied context (phandles, ``gpio_label``) or that
render as tied pairs (``clocks`` + ``clock-names``) are emitted by
overriding ``extra_dt_lines(context)``.

.. code-block:: python

   def extra_dt_lines(self, context: dict | None = None) -> list[str]:
       ctx = context or {}
       if self.clkin0_ref is not None:
           return [
               f"clocks = <&{self.clkin0_ref}>;",
               'clock-names = "clkin0";',
           ]
       return []

Component device models
-----------------------

Clock distributors and PLLs:

- :class:`adidt.devices.clocks.HMC7044`
- :class:`adidt.devices.clocks.AD9523_1`
- :class:`adidt.devices.clocks.AD9528`
- :class:`adidt.devices.clocks.AD9528_1`
- :class:`adidt.devices.clocks.ADF4382`

Converters / MxFE transceivers:

- :class:`adidt.devices.converters.AD9081` (with :class:`AD9081Adc`/:class:`AD9081Dac`)
- :class:`adidt.devices.converters.AD9084` (with :class:`AD9084Adc`/:class:`AD9084Dac`)
- :class:`adidt.devices.converters.AD9172`
- :class:`adidt.devices.converters.AD9680`
- :class:`adidt.devices.converters.AD9144`
- :class:`adidt.devices.converters.AD9152`

RF transceivers:

- :class:`adidt.devices.transceivers.ADRV9009` — reused for ADRV9025/9026/9029
  (Talise silicon) and for AD9371/ADRV9371 (Mykonos silicon).  The kernel
  binding differs per chip: set ``compatible_strings=["adi,ad9371"]`` plus
  ``node_name_base="ad9371-phy"`` for AD9371, otherwise the ADRV9009 default
  applies.

FPGA-side JESD204 IP overlays:

- :class:`adidt.devices.fpga_ip.Adxcvr` — AXI ADXCVR overlay
- :class:`adidt.devices.fpga_ip.Jesd204Overlay` — AXI JESD204 RX/TX overlay
- :class:`adidt.devices.fpga_ip.TplCore` — AXI TPL core overlay

Composition layer
-----------------

The composition API lives in :mod:`adidt.eval`, :mod:`adidt.fpga`, and
:mod:`adidt.system`:

.. code-block:: python

   import adidt

   fmc = adidt.eval.ad9081_fmc()
   fmc.converter.set_jesd204_mode(18, "jesd204c")
   fmc.converter.adc.sample_rate = int(250e6)
   fmc.converter.adc.cddc_decimation = 4
   fmc.converter.adc.fddc_decimation = 4

   fpga = adidt.fpga.zcu102()

   system = adidt.System(name="ad9081_zcu102", components=[fmc, fpga])
   system.connect_spi(bus_index=0, primary=fpga.spi[0],
                      secondary=fmc.clock.spi, cs=0)
   system.connect_spi(bus_index=1, primary=fpga.spi[1],
                      secondary=fmc.converter.spi, cs=0)
   system.add_link(source=fmc.converter.adc, sink=fpga.gt[0],
                   sink_reference_clock=fmc.dev_refclk,
                   sink_core_clock=fmc.core_clk_rx,
                   sink_sysref=fmc.dev_sysref)

   print(system.generate_dts())

- :class:`adidt.system.System` — collects devices + connection records,
  produces a :class:`~adidt.model.BoardModel`, delegates to
  :class:`~adidt.model.renderer.BoardModelRenderer` for DTS emission.
- :class:`adidt.eval.EvalBoard` subclasses (``ad9081_fmc``,
  ``ad9084_fmc``, ``adrv937x_fmc``) pre-wire a clock chip and a
  converter with the schematic-level channel assignments a specific FMC
  expects, and expose named clock-output aliases (``fmc.dev_refclk``,
  ``fmc.fpga_sysref``, …).
- :class:`adidt.fpga.FpgaBoard` subclasses (``zcu102``, ``vpk180``,
  ``zc706``) hold platform constants: address-cells, PS clock
  label/index, GPIO controller, SPI masters, GT lane count, default QPLL
  selection.

Writing a new device
--------------------

1. Subclass :class:`~adidt.devices.base.Device` (or a convenience base
   like :class:`~adidt.devices.clocks.ClockDevice` /
   :class:`~adidt.devices.converters.ConverterDevice`).
2. Declare ``compatible``, ``dt_header``, and ``dt_flags`` as class
   variables.
3. Declare pydantic fields for each DT property; use ``Field(alias=...)``
   with the DT property name.
4. If the device has sub-nodes, add a ``dict[int, SubModel]`` field
   annotated with :class:`DtSubnodes`.
5. Override ``extra_dt_lines`` for coupled / phandle properties.
6. Implement ``render_dt(cs=...)`` and ``to_component_model(...)``
   (the convenience bases do most of this for you).

See :mod:`adidt.devices.clocks.hmc7044` as the canonical full example.

End-to-end hardware verification
--------------------------------

Hardware tests live in ``test/hw/``.  Each exercises every stage —
XSA parsing → sdtgen → DTS generation → DTB compile → labgrid boot →
IIO + JESD204 link verification on real hardware.

- ``test_ad9081_zcu102_system_hw.py`` — AD9081 MxFE on ZCU102 via the
  declarative :class:`adidt.System` path.
- ``test_adrv9009_zcu102_hw.py`` — ADRV9009 on ZCU102 via the XSA
  pipeline (uses :class:`~adidt.xsa.builders.adrv9009.ADRV9009Builder`).
- ``test_adrv9371_zc706_hw.py`` — AD9371/ADRV9371 on ZC706 via the XSA
  pipeline (uses :class:`~adidt.xsa.builders.adrv937x.ADRV937xBuilder`),
  TFTP boot on Zynq-7000.

Tests support two connection modes, selected by ``.env`` at the project
root (loaded via ``pytest-dotenv``):

- **Coordinator mode** — set ``LG_COORDINATOR=<host>:<port>`` plus
  ``LG_ENV=<env_remote_*.yaml>``.  The env YAML binds a ``RemotePlace``
  to the coordinator-published resources.
- **Direct mode** — set ``LG_ENV=<local_yaml>`` only.

Example — run the ADRV9371+ZC706 test via a coordinator::

   LG_COORDINATOR=10.0.0.41:20408 \
   LG_ENV=env_remote_bq.yaml \
   pytest test/hw/test_adrv9371_zc706_hw.py

Copy ``.env.example`` to ``.env`` for the supported variables.  The skip
guard in each hw test module requires one of ``LG_COORDINATOR`` or
``LG_ENV`` to be set.
