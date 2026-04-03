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
3. **Node building** – each board builder constructs a ``BoardModel``
   (see :doc:`api/model`) from the XSA topology and config, then renders it
   to DTS node strings via Jinja2 templates.  The ``BoardModel`` is editable
   before rendering — callers can modify clock dividers, JESD parameters, or
   GPIO mappings programmatically.
4. **DTS merging** – inserts the rendered nodes into the base DTS, producing
   both a standalone overlay (``.dtso``) and a fully merged (``.dts``).
5. **HTML visualization** – generates a self-contained interactive report
   with D3.js topology, clock tree, and JESD204 parameter panels.
6. **Clock graph** – parses ``clocks`` / ``clock-names`` / ``clock-output-names``
   properties from the merged DTS and writes directed clock-distribution graphs
   in Graphviz DOT and D2 formats (SVG rendered automatically when ``dot`` /
   ``d2`` are available on PATH).

Pipeline diagram
~~~~~~~~~~~~~~~~

.. mermaid::

   flowchart LR
       XSA["Vivado .xsa"] --> SDT["sdtgen / lopper<br/>base DTS artifacts"]
       XSA --> HWH["HWH parser<br/>ADI IP topology"]
       CFG["pyadi-jif / JSON config<br/>JESD + clock settings"] --> NB["NodeBuilder<br/>BoardModel construction"]
       HWH --> NB
       NB --> BM["BoardModel<br/>editable board description"]
       BM --> RN["BoardModelRenderer<br/>ADI DTS nodes"]
       SDT --> MG["DtsMerger<br/>overlay + merged DTS"]
       RN --> MG
       MG --> DTBO["overlay .dtso"]
       MG --> DTS["merged .dts"]
       DTS --> DTC["dtc / cpp"]
       DTC --> DTB["system.dtb"]
       NB --> REP["HTML report<br/>topology + clocks + JESD"]
       DTS --> CG["ClockGraphGenerator<br/>clock-tree diagrams"]
       CG --> DOTF[".dot + .dot.svg"]
       CG --> D2F[".d2 + .d2.svg"]

       style XSA fill:#d6e8f7,stroke:#0067b9,color:#212836
       style CFG fill:#d6e8f7,stroke:#0067b9,color:#212836
       style SDT fill:#f0f4f8,stroke:#0067b9,color:#212836
       style HWH fill:#f0f4f8,stroke:#0067b9,color:#212836
       style NB fill:#f0f4f8,stroke:#0067b9,color:#212836
       style MG fill:#f0f4f8,stroke:#0067b9,color:#212836
       style DTC fill:#f0f4f8,stroke:#555,color:#212836
       style DTBO fill:#e8f0e8,stroke:#3a7d44,color:#212836
       style DTS fill:#e8f0e8,stroke:#3a7d44,color:#212836
       style DTB fill:#e8f0e8,stroke:#3a7d44,color:#212836
       style REP fill:#fff4e0,stroke:#c8940a,color:#212836
       style CG fill:#fff4e0,stroke:#c8940a,color:#212836
       style DOTF fill:#fff4e0,stroke:#c8940a,color:#212836
       style D2F fill:#fff4e0,stroke:#c8940a,color:#212836


Base DTS and Overlay Structure
------------------------------

The pipeline produces two output files: a **merged DTS** (``.dts``) and a
standalone **overlay** (``.dtso``).  Understanding what each contains — and
what the base DTS from ``sdtgen`` provides — is important when debugging boot
failures or integrating with custom HDL designs.

**Base DTS** (from ``sdtgen`` / ``lopper``)

``sdtgen`` generates a System Device Tree from the ``.hwh`` hardware handoff
inside the ``.xsa`` archive.  The base includes:

- The root ``/`` node with board and FPGA part identifiers.
- The ``amba_pl`` bus (``simple-bus``) containing **every AXI IP** in the
  Vivado block design — JESD204 controllers, DMA engines, SPI controllers,
  UART, Ethernet, GPIO, timer, interrupt controller, clock generators,
  transceivers, and memory controllers.
- Each IP node has ``compatible = "xlnx,..."``, ``reg``, ``interrupts``,
  and Xilinx-specific properties (``xlnx,ip-name``, ``xlnx,num-lanes``,
  etc.) derived from the HWH.
- CPU and memory nodes (``cpus``, ``memory@...``), ``chosen`` with
  ``stdout-path`` and ``bootargs``, and ``aliases`` for serial/SPI/I2C.
- Clock infrastructure: fixed-clock nodes and ``clk_bus_0`` providing the
  AXI bus clock.
- For MicroBlaze designs: the ``address-map`` property on the CPU node
  listing all accessible peripherals.

The base DTS nodes use Xilinx generic compatible strings
(``xlnx,axi-jesd204-rx-1.0``, ``xlnx,axi-dmac-1.0``, etc.) and lack
ADI-driver-specific properties.  The kernel can parse these nodes but
ADI drivers will not probe without the correct ``adi,...`` compatible and
configuration properties.

**What the pipeline adds** (overlay / merged nodes)

The ``NodeBuilder`` renders ADI-specific DTS content that either **replaces**
or **augments** nodes from the base:

*New nodes (inserted into the bus):*

- **AXI clock generators** — ``adi,axi-clkgen-2.00.a`` nodes with
  ``#clock-cells``, ``clock-output-names``, and bus clock references.
- **Fixed clocks** — e.g. ``clkin_125`` for external reference oscillators
  not described in the HWH.

*New SPI device child nodes:*

- **Clock chips** — HMC7044 (``adi,hmc7044``), AD9523-1 (``adi,ad9523-1``),
  or AD9528 (``adi,ad9528``) with PLL, VCXO, channel dividers, and
  JESD204 sysref-provider configuration.
- **PLLs** — ADF4382 (``adi,adf4382``) for converter device clocks.
- **Converters** — AD9084 (``adi,ad9084``), AD9081 (``adi,ad9081``),
  AD9680, AD9144, ADRV9009, etc., with JESD204 link parameters, firmware
  names, lane mappings, and GPIO connections.

These appear inside ``&spi_bus { ... }`` overlay blocks that add children
to the SPI controller nodes already present in the base.

*Overlay property additions* (``&label { ... }`` blocks):

- **DMA engines** — adds ``adi,axi-dmac-1.00.a`` compatible and
  ``#dma-cells`` to the existing DMA nodes.
- **ADXCVR transceivers** — adds ``adi,axi-adxcvr-1.0`` compatible,
  ``adi,sys-clk-select``, ``adi,out-clk-select``, clock references, and
  JESD204 input chain links.
- **JESD204 controllers** — adds ``adi,axi-jesd204-rx-1.0`` (or ``-tx-``),
  ``adi,octets-per-frame``, ``adi,frames-per-multiframe``, and the full
  ``jesd204-device`` / ``jesd204-inputs`` FSM framework properties.
- **TPL cores** — adds ``adi,axi-ad9081-rx-1.0`` (or board-specific
  variant), DMA links, and converter associations.
- **HSCI** — adds ``adi,axi-hsci-1.0.a`` and interface speed for
  high-speed converter interface blocks.

*Board fixups* (applied to the base before merging):

Some base DTS nodes require corrections that ``sdtgen`` cannot derive from
the HWH alone.  The ``board_fixups.py`` registry applies platform-specific
patches — for example, VCU118 Ethernet PHY configuration and IIO device
name normalization.

**Assumptions about the base DTS**

The pipeline expects the ``sdtgen``-generated base to provide:

1. An ``amba_pl`` (or ``amba``) bus node as the top-level container.
2. Labeled nodes for every AXI IP that the overlay will reference
   (``axi_apollo_rx_dma``, ``axi_apollo_rx_xcvr``, etc.).  The labels
   are derived from the Vivado block design instance names.
3. A ``clk_bus_0`` fixed-clock node providing the AXI bus clock frequency.
4. Correct ``#address-cells`` and ``#size-cells`` on the bus (1 for
   MicroBlaze/VCU118, 2 for ZynqMP/ZCU102).
5. For MicroBlaze: a ``cpus`` node, ``memory`` node with ``device_type``,
   and ``chosen`` with ``bootargs = "earlycon"`` and ``stdout-path`` pointing
   to the UART.  The ``SdtgenRunner`` applies fixups to ensure these are
   present.

If the XSA comes from an ADI HDL reference design, these assumptions hold
automatically.  Custom designs must follow the same naming conventions for
the overlay labels to resolve.

**Merged vs overlay output**

- The **merged DTS** (``.dts``) combines the base and overlay into a single
  file with ``#include "pl.dtsi"`` for the base, followed by the generated
  ADI nodes and ``&label { ... }`` augmentations.  Compile it with
  ``cpp + dtc`` to produce a standalone DTB.

- The **overlay** (``.dtso``) is a ``/plugin/;`` file that can be applied
  at runtime via ``dtoverlay`` on systems that support dynamic DT overlays.
  It contains the same ADI nodes but uses ``&amba_pl { ... }`` to target
  the bus node.

For MicroBlaze ``simpleImage`` targets, use the merged DTS — overlays
require a base DTB that the bootloader applies the overlay to, which
MicroBlaze's direct-boot flow does not support.

Hardware Test Flow
------------------

The hardware tests can optionally build and inject a kernel image with
``pyadi-build`` while still using the DTB generated from the XSA pipeline.

.. mermaid::

   flowchart TD
       KREL["Kuiper release BOOT.BIN"] --> DEPLOY["KuiperDLDriver deploy"]
       XSA2["XSA from examples<br/>or Kuiper project"] --> PIPE["XsaPipeline.run()"]
       CFG2["board config<br/>(JSON or adijif-derived)"] --> PIPE
       PIPE --> MDTS["merged DTS"]
       MDTS --> COMPILE["cpp + dtc"]
       COMPILE --> MDTB["generated system.dtb"]
       PYB{"ADI_XSA_BUILD_KERNEL=1 ?"} -->|yes| PBUILD["pyadi-build<br/>build kernel image"]
       PYB -->|no| SKIP["skip kernel replacement"]
       PBUILD --> DEPLOY
       MDTB --> DEPLOY
       SKIP --> DEPLOY
       DEPLOY --> BOOT["boot target via labgrid"]
       BOOT --> CHECK["run checks on DUT shell<br/>dmesg + jesd_status + IIO devices"]

       style XSA2 fill:#d6e8f7,stroke:#0067b9,color:#212836
       style CFG2 fill:#d6e8f7,stroke:#0067b9,color:#212836
       style KREL fill:#d6e8f7,stroke:#0067b9,color:#212836
       style PIPE fill:#f0f4f8,stroke:#0067b9,color:#212836
       style MDTS fill:#e8f0e8,stroke:#3a7d44,color:#212836
       style COMPILE fill:#f0f4f8,stroke:#555,color:#212836
       style MDTB fill:#e8f0e8,stroke:#3a7d44,color:#212836
       style PYB fill:#fff4e0,stroke:#c8940a,color:#212836
       style PBUILD fill:#fff4e0,stroke:#c8940a,color:#212836
       style SKIP fill:#f0f4f8,stroke:#555,color:#212836
       style DEPLOY fill:#f0f4f8,stroke:#0067b9,color:#212836
       style BOOT fill:#f0f4f8,stroke:#0067b9,color:#212836
       style CHECK fill:#e8f0e8,stroke:#3a7d44,color:#212836

Example hardware invocation:

.. code-block:: bash

   source /tools/Xilinx/2025.1/Vivado/settings64.sh
   LG_ENV=/jenkins/lg_ad9081_zcu102.yaml ADI_XSA_BUILD_KERNEL=1 \
     pytest -q test/hw/ad9081/test_ad9081_xsa_hw_m4_l8.py

Installation
------------

The XSA pipeline requires ``lopper`` (the Xilinx System Device Tree
generator). Install the optional dependency group:

.. code-block:: bash

   pip install "adidt[xsa]"

Usage
-----

Start with the step-by-step tutorial before tuning profiles:

.. code-block:: bash

   python examples/xsa/adrv9009_zcu102.py --xsa /path/to/design.xsa

or use the full-page tutorial at
:doc:`examples/xsa_tutorial` and the adijif-focused guide
:doc:`examples/xsa_adijif_tutorial`.

Run the pipeline from the CLI:

.. code-block:: bash

   adidtc xsa2dt -x design.xsa -c config.json -o out/

Select an explicit board profile (optional):

.. code-block:: bash

   adidtc xsa2dt -x design.xsa -c config.json --profile ad9081_zcu102 -o out/

Generate manifest parity reports from a reference DTS root:

.. code-block:: bash

   adidtc xsa2dt -x design.xsa -c config.json -o out/ \
     --reference-dts zynqmp-zcu102-rev10-ad9081-m8-l4.dts

Enable strict parity mode to fail generation when required roles are missing:

.. code-block:: bash

   adidtc xsa2dt -x design.xsa -c config.json -o out/ \
     --reference-dts zynqmp-zcu102-rev10-ad9081-m8-l4.dts \
     --strict-parity

List available built-in profiles:

.. code-block:: bash

   adidtc xsa-profiles

Show one profile and its defaults:

.. code-block:: bash

   adidtc xsa-profile-show ad9081_zcu102

Built-in profiles
~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 25 20 20 15 20
   :header-rows: 1

   * - Profile
     - Converter Family
     - Platform
     - JESD in Profile
     - Board Config Key
   * - ``ad9081_zcu102``
     - AD9081 MxFE
     - ZCU102
     - No (supply via cfg)
     - ``ad9081_board``
   * - ``ad9081_zc706``
     - AD9081 MxFE
     - ZC706
     - No (supply via cfg)
     - ``ad9081_board``
   * - ``ad9082_zcu102``
     - AD9082 MxFE
     - ZCU102
     - No (supply via cfg)
     - ``ad9081_board``
   * - ``ad9083_zcu102``
     - AD9083 MxFE
     - ZCU102
     - No (supply via cfg)
     - ``ad9081_board``
   * - ``ad9084_vcu118``
     - AD9084
     - VCU118
     - Yes
     - ``ad9084_board``
   * - ``ad9172_zcu102``
     - AD9172 DAC
     - ZCU102
     - Yes
     - ``ad9172_board``
   * - ``adrv9009_zcu102``
     - ADRV9009
     - ZCU102
     - No (supply via cfg)
     - ``adrv9009_board``
   * - ``adrv9009_zc706``
     - ADRV9009
     - ZC706
     - No (supply via cfg)
     - ``adrv9009_board``
   * - ``adrv9025_zcu102``
     - ADRV9025
     - ZCU102
     - No (supply via cfg)
     - ``adrv9009_board``
   * - ``adrv9008_zcu102``
     - ADRV9008
     - ZCU102
     - No (supply via cfg)
     - ``adrv9009_board``
   * - ``adrv9008_zc706``
     - ADRV9008
     - ZC706
     - No (supply via cfg)
     - ``adrv9009_board``
   * - ``adrv937x_zcu102``
     - ADRV937x
     - ZCU102
     - No (supply via cfg)
     - ``adrv9009_board``
   * - ``adrv937x_zc706``
     - ADRV937x
     - ZC706
     - No (supply via cfg)
     - ``adrv9009_board``
   * - ``adrv9002_zc706``
     - ADRV9002
     - ZC706
     - No (supply via cfg)
     - —
   * - ``fmcdaq2_zcu102``
     - FMCDAQ2
     - ZCU102
     - No (supply via cfg)
     - ``fmcdaq2_board``
   * - ``fmcdaq2_zc706``
     - FMCDAQ2
     - ZC706
     - No (supply via cfg)
     - ``fmcdaq2_board``
   * - ``fmcdaq3_zcu102``
     - FMCDAQ3
     - ZCU102
     - Yes
     - ``fmcdaq3_board``
   * - ``fmcdaq3_zc706``
     - FMCDAQ3
     - ZC706
     - Yes
     - ``fmcdaq3_board``

Profiles with **"JESD in Profile = Yes"** include default JESD framing
parameters (F, K, M, L, Np, S) and can be used with ``cfg={}`` — no user
config needed.  Profiles with **"No"** require JESD parameters to be supplied
via the ``cfg`` dict, typically from a ``pyadi-jif`` solver or manual
configuration.

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
   print(results["merged"])       # Path to the merged .dts
   print(results["report"])       # Path to the HTML visualization
   print(results["clock_dot"])    # Path to the Graphviz clock-tree .dot
   print(results["clock_d2"])     # Path to the D2 clock-tree .d2
   # SVG paths are present only when the rendering tool is installed:
   # results["clock_dot_svg"], results["clock_d2_svg"]

Python API
----------

Core classes and methods used in the XSA flow:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - API
     - Purpose
   * - ``XsaParser.parse(xsa_path: Path) -> XsaTopology``
     - Extracts ``.hwh`` from the XSA and returns discovered JESD, clockgen,
       converter, connectivity, and part metadata.
   * - ``NodeBuilder.build(topology: XsaTopology, cfg: dict) -> dict[str, list[str]]``
     - Dispatches to board builders, each constructing a ``BoardModel`` and
       rendering it via ``BoardModelRenderer``.
   * - ``BoardModelRenderer.render(model: BoardModel) -> dict[str, list[str]]``
     - Renders a ``BoardModel`` to DTS node strings using per-component
       Jinja2 templates.  See :doc:`api/model`.
   * - ``DtsMerger.merge(base_dts: str, nodes: dict, output_dir: Path, name: str)``
     - Produces ``<name>.dtso`` overlay + ``<name>.dts`` merged full tree.
   * - ``HtmlVisualizer.generate(topology, cfg, merged_content, output_dir, name)``
     - Writes self-contained HTML debug report with topology and clock links.
   * - ``ClockGraphGenerator.generate(merged_dts, output_dir, name) -> dict[str, Path]``
     - Parses clock properties from the merged DTS and writes ``.dot`` and
       ``.d2`` clock-tree diagrams; renders SVG when ``dot`` / ``d2`` are on PATH.
   * - ``XsaPipeline.run(...) -> dict[str, Path]``
     - Orchestrates all stages end-to-end and returns artifact paths.

``XsaPipeline.run`` argument reference
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Argument
     - Type
     - Description
   * - ``xsa_path``
     - ``Path``
     - Vivado hardware handoff archive (must contain one ``.hwh``).
   * - ``cfg``
     - ``dict``
     - Runtime configuration (JESD, clock labels/channels, board overrides).
   * - ``output_dir``
     - ``Path``
     - Output folder for base SDT, overlay/merged DTS, and report artifacts.
   * - ``sdtgen_timeout``
     - ``int``
     - Timeout (seconds) for SDT generation subprocess.
   * - ``profile``
     - ``str | None``
     - Optional explicit built-in/custom profile name.
   * - ``reference_dts``
     - ``Path | None``
     - Optional DTS root for manifest-parity checks and coverage artifacts.
   * - ``strict_parity``
     - ``bool``
     - If true, raises ``ParityError`` when required roles/links/properties
       are missing/mismatched.

Using adijif (pyadi-jif) With the XSA Flow
------------------------------------------

The intended integration is:

1. Use ``adijif`` to select/solve JESD and clock settings.
2. Translate solved values into ``cfg`` keys expected by ``XsaPipeline``.
3. Run ``XsaPipeline`` with either explicit profile or auto-profile.
4. Compile the generated merged DTS to DTB and deploy/test on hardware.

adijif integration workflow
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   flowchart LR
       AJ["adijif system()<br/>converter + clock + fpga model"] --> MODE["select JESD modes<br/>M/L/F/K/Np/S"]
       MODE --> SOLVE{"run solve()?"}
       SOLVE -->|yes| SCFG["read solved clock /<br/>JESD outputs"]
       SOLVE -->|no| QCFG["use quick mode<br/>settings"]
       SCFG --> MAP["map to XsaPipeline<br/>cfg keys"]
       QCFG --> MAP
       MAP --> PIPE2["XsaPipeline.run()"]
       PIPE2 --> DTS2["merged DTS +<br/>overlay + report"]
       DTS2 --> DTB2["cpp + dtc →<br/>system.dtb"]
       DTB2 --> HW2["boot + dmesg +<br/>jesd_status validation"]

       style AJ fill:#d6e8f7,stroke:#0067b9,color:#212836
       style MODE fill:#f0f4f8,stroke:#0067b9,color:#212836
       style SOLVE fill:#fff4e0,stroke:#c8940a,color:#212836
       style SCFG fill:#f0f4f8,stroke:#0067b9,color:#212836
       style QCFG fill:#f0f4f8,stroke:#0067b9,color:#212836
       style MAP fill:#f0f4f8,stroke:#0067b9,color:#212836
       style PIPE2 fill:#f0f4f8,stroke:#0067b9,color:#212836
       style DTS2 fill:#e8f0e8,stroke:#3a7d44,color:#212836
       style DTB2 fill:#e8f0e8,stroke:#3a7d44,color:#212836
       style HW2 fill:#e8f0e8,stroke:#3a7d44,color:#212836

adijif-to-config mapping
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - adijif output
     - ``cfg`` key in XSA flow
   * - RX JESD ``F, K, M, L, Np, S``
     - ``cfg["jesd"]["rx"]``
   * - TX JESD ``F, K, M, L, Np, S``
     - ``cfg["jesd"]["tx"]``
   * - RX device clock source choice
     - ``cfg["clock"]["rx_device_clk_label"]`` (for example ``clkgen``/``hmc7044``)
   * - TX device clock source choice
     - ``cfg["clock"]["tx_device_clk_label"]``
   * - HMC/clock output channel for RX
     - ``cfg["clock"]["hmc7044_rx_channel"]``
   * - HMC/clock output channel for TX
     - ``cfg["clock"]["hmc7044_tx_channel"]``
   * - Board wiring specifics (SPI/CS/GPIO/link IDs)
     - ``ad9081_board`` / ``adrv9009_board`` / ``fmcdaq2_board`` profile keys

Reference implementation
~~~~~~~~~~~~~~~~~~~~~~~~

Use the ADRV9009 example for a complete adijif-driven flow:

- ``examples/xsa/adrv9009_zcu102.py``

For ADRV9025 ZCU102 XSA flows (Kuiper/local XSA), use:

- ``examples/xsa/adrv9025_zcu102.py``

The script demonstrates both quick-mode JESD extraction and optional
``solve()`` usage, then feeds those values directly into ``XsaPipeline``.

You can also pass ``profile="ad9081_zcu102"`` (or another built-in profile) to
``XsaPipeline.run()``. If no profile is passed, the pipeline will auto-select a
matching profile when available (for example, ``ad9081_zcu102``).

For AD9082 Kuiper projects, prefer explicit profile selection:
``profile="ad9082_zcu102"``. AD9081/AD9082 designs often share ``mxfe`` JESD
instance names, so topology-only auto-inference is ambiguous.

For AD9083 Kuiper projects, prefer explicit profile selection:
``profile="ad9083_zcu102"`` for the same reason (shared ``mxfe`` naming).

For AD9081 ZC706 Kuiper projects, use:
``profile="ad9081_zc706"``.

For AD9172 Kuiper projects, use explicit profile selection:
``profile="ad9172_zcu102"``. XSA provides JESD/clock transport topology while
SPI-attached DAC/clock chip details require board-specific overlays.

Auto-selection also covers FMCDAQ2 variants:

- ``fmcdaq2_zcu102`` (ZynqMP/ZCU102)
- ``fmcdaq2_zc706`` (Zynq-7000/ZC706)

FMCDAQ3 variants are available via explicit profiles:

- ``fmcdaq3_zcu102``
- ``fmcdaq3_zc706``

Current FMCDAQ3 support focuses on JESD/clock transport defaults and artifact
generation; board-specific SPI device overlay content remains to be extended.

ADRV family profile variants include:

- ``adrv9008_zcu102``
- ``adrv9008_zc706``
- ``adrv9002_zc706``
- ``adrv9009_zc706``
- ``adrv9009_zcu102``
- ``adrv937x_zc706``
- ``adrv937x_zcu102``
- ``adrv9025_zcu102`` (also selected from ``adrv9026``-named JESD labels)

The ``adrv9009_zcu102`` profile also supports the **AD-FMCOMMS8-EBZ**
(FMComms8) dual-chip design.  When the XSA topology is detected as
FMComms8 layout (two ADRV9009 transceivers sharing one SPI bus), the
pipeline generates a second PHY node (``trx1_adrv9009``) with independent
HMC7044 channel assignments per chip:

- trx0 (``adrv9009-x2``): uses HMC7044 channels 0/1 (dev/sysref) and 6 (FPGA sysref)
- trx1 (``adrv9009``): uses HMC7044 channels 2/3 (dev/sysref) and 7 (FPGA sysref)

Hardware tests verify that both ``adrv9009-phy`` IIO devices appear in
the IIO context.

For ADRV9008 Kuiper projects, prefer explicit profile selection:
``profile="adrv9008_zcu102"``. Many ADRV9008 XSAs use ADRV9009-style JESD/IP
instance names, which makes converter-family auto-inference ambiguous.

AD9084 (Apollo) VCU118 MicroBlaze support
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The pipeline supports AD9084 "apollo" dual-link designs on VCU118 (MicroBlaze).
These designs feature four JESD204C links (RX A/B + TX A/B) with separate
XCVR, DMA, and TPL cores per link.  The board builder generates nodes for:

- **ADF4382** PLL (reference clock for AD9084 dev_clk)
- **HMC7044** clock distributor (JESD reference clocks, SYSREF)
- **HSCI** high-speed connector interface
- **JESD204 overlay** nodes with 4-clock config (s_axi_aclk, link_clk,
  device_clk, lane_clk) and per-link device clock from HMC7044 channels
- **AD9084** converter node with profile firmware, lane mappings, and HSCI

The built-in ``ad9084_vcu118`` profile encodes the AD9084-EBZ board wiring
for the HMC7044 + AD9084 + ADF4382 combination. When the pipeline sees an
AD9084 design on VCU118 it now auto-applies those defaults unless the caller
overrides them explicitly.

Configuration uses the ``ad9084_board`` key with JESD204 link IDs from
``dt-bindings/iio/adc/adi,ad9088.h``:

.. code-block:: python

   cfg = {
       "jesd": {
           "rx": {"F": 6, "K": 32, "M": 4, "L": 8, "Np": 12, "S": 1},
           "tx": {"F": 6, "K": 32, "M": 4, "L": 8, "Np": 12, "S": 1},
       },
       "clock": {
           "rx_device_clk_label": "hmc7044",
           "rx_device_clk_index": 8,
           "tx_device_clk_label": "hmc7044",
           "tx_device_clk_index": 9,
           "rx_b_device_clk_index": 11,
           "tx_b_device_clk_index": 12,
       },
       "ad9084_board": {
           "converter_spi": "axi_spi_2",
           "converter_cs": 0,
           "clock_spi": "axi_spi",
           "hmc7044_cs": 1,
           "adf4382_cs": 0,
           "dev_clk_ref": "adf4382 0",
           "dev_clk_scales": "1 10",
           "firmware_name": "204C_M4_L8_NP16_1p25_4x4.bin",
           "reset_gpio": 62,
           "rx_a_link_id": 4,   # FRAMER_LINK_A0_RX
           "rx_b_link_id": 6,   # FRAMER_LINK_B0_RX
           "tx_a_link_id": 0,   # DEFRAMER_LINK_A0_TX
           "tx_b_link_id": 2,   # DEFRAMER_LINK_B0_TX
           "hsci_label": "axi_hsci_0",
           "hsci_auto_linkup": True,
           # ... lane mappings, HMC7044 channel config, etc.
       },
   }

The sdtgen postprocessor applies MicroBlaze-specific fixups (CPU cluster
rename, DDR4 memory node, earlycon bootargs) and the node builder uses
platform-aware ``reg_addr()``/``reg_size()`` for 32-bit register format.

See ``test/ad9084/test_ad9084_xsa_hw_vcu118.py`` for a complete hardware test
example that runs the full pipeline and verifies all IIO devices and JESD204C
links.

If ``reference_dts=Path(...)`` is passed to ``XsaPipeline.run()``, the pipeline
also writes parity artifacts:

- ``<name>.map.json`` – role and required-link parity summary
- ``<name>.coverage.md`` – human-readable role/link/property coverage report
  (property checks are value-sensitive)

When ``strict_parity=True`` is used with ``reference_dts``, the pipeline raises
``ParityError`` if any required manifest roles, links, or properties are
missing in the generated DTS.

For properties, parity checks compare both property name and value from the
reference DTS role node. Value comparison is whitespace-insensitive.

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

AD9081 link-mode resolution
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For AD9081 + MXFE XSA designs, ``NodeBuilder`` resolves
``adi,link-mode`` using this precedence:

1. ``cfg["ad9081"]["rx_link_mode"]`` / ``cfg["ad9081"]["tx_link_mode"]``
2. ``cfg["jesd"]["rx"]["mode"]`` / ``cfg["jesd"]["tx"]["mode"]``
3. Inference from JESD ``(M, L)`` tuples:

   - ``(8, 4)`` -> RX ``17``, TX ``18``
   - ``(4, 8)`` -> RX ``10``, TX ``11``

If no explicit mode is set and ``(M, L)`` does not match a supported tuple,
``ConfigError`` is raised instead of silently falling back to hardcoded modes.

Board override keys
~~~~~~~~~~~~~~~~~~~

The profile/default config can carry board-specific keys to avoid hardcoding in
the parser implementation.

``ad9081_board`` keys:

- ``clock_spi`` / ``clock_cs`` – SPI bus and chip-select for HMC7044
- ``adc_spi`` / ``adc_cs`` – SPI bus and chip-select for AD9081
- ``reset_gpio`` / ``sysref_req_gpio`` / ``rx1_enable_gpio`` /
  ``rx2_enable_gpio`` / ``tx1_enable_gpio`` / ``tx2_enable_gpio``
- ``hmc7044_channel_blocks`` – optional replacement list for HMC7044 channel
  subnodes (raw DTS snippet blocks)

``adrv9009_board`` keys:

- ``misc_clk_hz`` – fixed clock frequency for ``misc_clk_0``
- ``spi_bus`` / ``clk_cs`` / ``trx_cs`` – SPI and CS assignments
- ``trx_reset_gpio`` / ``trx_sysref_req_gpio`` / ``trx_spi_max_frequency``
- ``ad9528_vcxo_freq``
- ``rx_link_id`` / ``rx_os_link_id`` / ``tx_link_id``
- ``tx_octets_per_frame`` / ``rx_os_octets_per_frame``
- ``trx_profile_props`` – optional replacement list for ADRV9009 PHY profile
  properties (raw DTS property lines)
- ``ad9528_channel_blocks`` – optional replacement list for AD9528 channel
  subnodes (raw DTS snippet blocks)

``fmcdaq2_board`` keys:

- ``spi_bus`` / ``clock_cs`` / ``adc_cs`` / ``dac_cs`` – SPI bus and chip-select
  assignments (default mapping: AD9523 on CS0, AD9144 on CS1, AD9680 on CS2)
- ``clock_vcxo_hz`` / ``clock_spi_max_frequency`` /
  ``adc_spi_max_frequency`` / ``dac_spi_max_frequency``
- ``adc_dma_label`` / ``dac_dma_label``
- ``adc_core_label`` / ``dac_core_label``
- ``adc_xcvr_label`` / ``dac_xcvr_label``
- ``adc_jesd_label`` / ``dac_jesd_label``
- ``adc_jesd_link_id`` / ``dac_jesd_link_id``
- ``adc_device_clk_idx`` / ``adc_sysref_clk_idx`` /
  ``adc_xcvr_ref_clk_idx`` / ``dac_device_clk_idx`` /
  ``dac_xcvr_ref_clk_idx``
- ``adc_sampling_frequency_hz``
- GPIO overrides: ``clk_sync_gpio``, ``clk_status0_gpio``, ``clk_status1_gpio``,
  ``dac_txen_gpio``, ``dac_reset_gpio``, ``dac_irq_gpio``,
  ``adc_powerdown_gpio``, ``adc_fastdetect_a_gpio``, ``adc_fastdetect_b_gpio``

Hardware test note
~~~~~~~~~~~~~~~~~~

Some XSA-derived FMCDAQ2 designs expose tpl-core IIO names instead of legacy
core names. Hardware tests therefore accept either set:

- legacy: ``axi-ad9680-hpc``, ``axi-ad9144-hpc``
- tpl-core: ``ad_ip_jesd204_tpl_adc``, ``ad_ip_jesd204_tpl_dac``

Profile validation
~~~~~~~~~~~~~~~~~~

Built-in and custom JSON profiles are validated when loaded:

- Unknown keys under ``ad9081_board`` / ``adrv9009_board`` raise
  ``ProfileError`` (prevents silent typos).
- Structured snippet fields such as ``hmc7044_channel_blocks``,
  ``ad9528_channel_blocks``, and ``trx_profile_props`` must be JSON lists.

``merge_profile_defaults()`` deep-copies defaults during merge so mutating the
effective runtime config does not mutate the source profile data.

Supported IP Cores
------------------

The XSA parser recognises the following ADI IP cores:

.. list-table::
   :widths: 45 55
   :header-rows: 1

   * - IP type (``MODTYPE``)
     - Role
   * - ``axi_jesd204_rx``, ``axi_jesd204_tx``
     - JESD204 FSM controllers
   * - ``axi_clkgen``
     - PL clock generator
   * - ``axi_ad9081``, ``axi_ad9084``, ``axi_ad9375``
     - RF data converters

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

=================  ============================================
Key                Description
=================  ============================================
``base_dir``       Directory containing the sdtgen output
``overlay``        ``.dtso`` overlay (ADI nodes only)
``merged``         ``.dts`` with base SDT + ADI nodes merged
``report``         Self-contained HTML visualisation report
``clock_dot``      Graphviz DOT clock-tree diagram (always)
``clock_d2``       D2 clock-tree diagram (always)
``clock_dot_svg``  SVG rendered from DOT (when ``dot`` is on PATH)
``clock_d2_svg``   SVG rendered from D2 (when ``d2`` is on PATH)
``map``            (Optional) manifest parity JSON report
``coverage``       (Optional) manifest parity Markdown summary
=================  ============================================

Clock Topology Graphs
---------------------

``XsaPipeline.run()`` automatically produces clock-tree diagrams derived
from the merged DTS.  Both output formats are written unconditionally; SVG
renderings are produced alongside each when the corresponding tool is on
PATH.

.. list-table::
   :widths: 20 20 60
   :header-rows: 1

   * - File
     - Tool for SVG
     - Notes
   * - ``<name>_clocks.dot``
     - ``dot`` (Graphviz)
     - Graphviz directed graph; render manually with
       ``dot -Tsvg -o clocks.svg <name>_clocks.dot``
   * - ``<name>_clocks.d2``
     - ``d2``
     - D2lang diagram; render manually with
       ``d2 <name>_clocks.d2 clocks.svg``

Both formats use the same colour scheme:

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Node type
     - Colour / shape
   * - PS clocks (``zynqmp_clk``, ``ps7_clkc``)
     - Orange, oval
   * - Clock chips (``hmc7044``, ``ad9528``, ``ad9523``)
     - Dark blue, rectangle
   * - GT transceivers (``*xcvr*``)
     - Purple, rectangle
   * - JESD204 controllers (``*jesd*``)
     - Dark green, rectangle
   * - PL clock generators (``*clkgen*``)
     - Teal, rectangle
   * - Converters / PHY (``trx*``, ``ad9*``, ``adrv*``)
     - Dark red, rectangle

Edges are labelled with the ``clock-names`` value and the provider channel
index (e.g. ``device_clk[9]``).  Edge styles distinguish signal-domain
clocks from AXI bus clocks:

- **Solid coloured** – ``device_clk`` (blue), ``lane_clk`` (green),
  ``conv`` (gold), ``sampl_clk`` (purple)
- **Dashed** – ``s_axi_aclk`` (grey), ``div40`` (gold dashed)

The graphs can also be generated standalone without running the full
pipeline:

.. code-block:: python

   from pathlib import Path
   from adidt.xsa.clock_graph import ClockGraphGenerator

   merged_dts = Path("out/adrv9009_zcu102.dts").read_text()
   result = ClockGraphGenerator().generate(merged_dts, Path("out/"), "adrv9009_zcu102")
   print(result["clock_dot"])    # always present
   print(result["clock_d2"])     # always present
   # result["clock_dot_svg"] and result["clock_d2_svg"] when tools are available

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
   * - ``ParityError``
     - Strict parity mode is enabled and one or more required roles are missing
   * - ``SdtgenNotFoundError``
     - The ``sdtgen`` / ``lopper`` binary cannot be found on ``PATH``
   * - ``SdtgenError``
     - ``sdtgen`` exits with a non-zero return code
