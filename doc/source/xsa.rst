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

Pipeline diagram
~~~~~~~~~~~~~~~~

.. mermaid::

   flowchart LR
       XSA["Vivado .xsa"] --> SDT["sdtgen/lopper<br/>base DTS artifacts"]
       XSA --> HWH["HWH parser<br/>ADI IP topology"]
       CFG["pyadi-jif / JSON config<br/>JESD + clock settings"] --> NB["NodeBuilder<br/>ADI DTS nodes"]
       HWH --> NB
       SDT --> MG["DtsMerger<br/>overlay + merged DTS"]
       NB --> MG
       MG --> DTBO["overlay .dtso"]
       MG --> DTS["merged .dts"]
       DTS --> DTC["dtc/cpp"]
       DTC --> DTB["system.dtb"]
       NB --> REP["HTML report<br/>topology + clocks + JESD"]

Hardware test flow with ``pyadi-build``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The hardware tests can optionally build and inject a kernel image with
``pyadi-build`` while still using the DTB generated from the XSA pipeline.

.. mermaid::

   flowchart TD
       KREL["Kuiper release BOOT.BIN"] --> DEPLOY["KuiperDLDriver deploy"]
       XSA2["XSA from examples or Kuiper project"] --> PIPE["XsaPipeline.run()"]
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

Run the pipeline from the CLI:

.. code-block:: bash

   adidtc xsa2dt design.xsa config.json --output-dir out/

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
     - Renders ADI DTS node blocks for converters/JESD/clocking using profile
       defaults and runtime config.
   * - ``DtsMerger.merge(base_dts: str, nodes: dict, output_dir: Path, name: str)``
     - Produces ``<name>.dtso`` overlay + ``<name>.dts`` merged full tree.
   * - ``HtmlVisualizer.generate(topology, cfg, merged_content, output_dir, name)``
     - Writes self-contained HTML debug report with topology and clock links.
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
       SOLVE -->|yes| SCFG["read solved clock/JESD outputs"]
       SOLVE -->|no| QCFG["use quick mode settings"]
       SCFG --> MAP["map to XsaPipeline cfg keys"]
       QCFG --> MAP
       MAP --> PIPE2["XsaPipeline.run()"]
       PIPE2 --> DTS2["merged DTS + overlay + report"]
       DTS2 --> DTB2["cpp + dtc -> system.dtb"]
       DTB2 --> HW2["boot + dmesg + jesd_status validation"]

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
- ``adrv9009_zc706``
- ``adrv9009_zcu102``
- ``adrv937x_zc706``
- ``adrv937x_zcu102``
- ``adrv9025_zcu102`` (also selected from ``adrv9026``-named JESD labels)

For ADRV9008 Kuiper projects, prefer explicit profile selection:
``profile="adrv9008_zcu102"``. Many ADRV9008 XSAs use ADRV9009-style JESD/IP
instance names, which makes converter-family auto-inference ambiguous.

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

============  ============================================
Key           Description
============  ============================================
``base_dir``  Directory containing the sdtgen output
``overlay``   ``.dtso`` overlay (ADI nodes only)
``merged``    ``.dts`` with base SDT + ADI nodes merged
``report``    Self-contained HTML visualisation report
``map``       (Optional) manifest parity JSON report
``coverage``  (Optional) manifest parity Markdown summary
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
   * - ``ParityError``
     - Strict parity mode is enabled and one or more required roles are missing
   * - ``SdtgenNotFoundError``
     - The ``sdtgen`` / ``lopper`` binary cannot be found on ``PATH``
   * - ``SdtgenError``
     - ``sdtgen`` exits with a non-zero return code
