# Changelog

All notable changes to pyadi-dt are documented here. The project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Profiles for 14 more HDL 2026.1 designs, seeded from XSAs built from the
  HDL sources: AD9081, AD9082 and AD9084 on VCK190 and VPK180, AD9209 on
  VCK190, AD9081, AD9082, dual AD9208 and ADRV9026 on VCU118, and ADRV9371,
  DAQ2, DAQ3 and FMCOMMS2 on KCU105.
- XSA interrupt resolution for Versal (`pl_ps_irq`) and MicroBlaze
  (`axi_intc` inputs); the profile seeder handles MicroBlaze systems, whose
  design and carrier cores share one bus.
- Coverage gate for designs a release ships no XSA for (PDI-only Versal boot
  files, MicroBlaze carriers without boot files):
  `scripts/build_hdl_release_xsas.sh` exports their XSAs from the HDL sources
  without running synthesis, `ADI_XSA_LOCAL_DIR` points the gate and
  `scripts/seed_declarative_profile.py --local-xsa-dir` at them, and the
  inventory's `local_xsa` field names the kernel reference of each default
  build.

- Inventory of every Xilinx design in the HDL 2026.1 release
  (`adidt/xsa/config/hdl_2026_r1_designs.json`), joined to its kernel
  reference device trees and Kuiper boot directories, with
  `scripts/generate_hdl_release_inventory.py` to regenerate it and an
  opt-in coverage gate (`test/xsa/test_hdl_release_coverage.py`) that runs
  the pipeline on every released XSA.
- Declarative design profiles: a profile's `design` section lists the PL
  cores and bus devices of an HDL design, and `DeclarativeBuilder` renders
  them with addresses and interrupts taken from the XSA.
  `scripts/seed_declarative_profile.py` seeds these profiles from the kernel
  reference device trees.
- Seeded profiles for every HDL 2026.1 design that ships an XSA and has no
  hand-written builder (87 boot directories across 52 designs: FMComms2/5,
  ADRV9001, the ADRV936x SoMs, AD9082/AD9083, `dac_fmc_ebz`, FMComms8, the
  SPI-engine and parallel-interface converters, CN0506 and the ADV7511 base
  designs), plus unvalidated profiles for six Zynq/ZynqMP designs the
  release ships no XSA for.  `doc/source/hdl_2026_r1_support.rst` lists the
  state of every design.
- The XSA parser reads the HDL project, carrier and build variant from the
  system-ID ROM path (`XsaTopology.hdl_project`, `hdl_carrier`,
  `hdl_variant`), and profile auto-selection uses that identity first.
- The coverage gate checks that every ADI driver binding in the kernel
  reference tree is present in the generated tree
  (`adidt.xsa.validate.bindings`).
- JESD204 framing (M, L, S, N, Np, F and a default K) is read from the XSA's
  transport-layer cores when the configuration leaves it out.
- Platform detection for ZedBoard, ZC702, Cora Z7S, the ADRV9361/ADRV9364
  SoMs, VCK190, VMK180, KCU105, KC705, VC707, VC709, AC701 and VCU128, using
  the XSA's board file to tell ZedBoard and ZC702 apart.

### Changed
- The HDL 2026.1 inventory is pinned to the `2026.1.0` release tag. The tag
  removes 45 projects that are not part of the release, so the inventory
  lists 79 designs, all supported. Profiles for the ten removed designs that
  had one are kept but are no longer checked by the coverage gate.

- `kuiper_boards.json` now describes the Kuiper 2026_r1 boot partition.
- Zynq-7000 carriers other than ZC706 now use one address cell and the
  `clkc`/`gpio0` labels instead of the ZynqMP defaults.
- Profile auto-selection looks for a profile declared for the XSA's HDL
  design before falling back to `<converter_family>_<platform>`.  AD9082,
  AD9083, ADRV9002 on ZCU102, ADRV9025, the `dac_fmc_ebz` DACs and the
  FMComms8 variants now select their seeded profile.
- PL interrupt numbers are resolved from the XSA on Zynq-7000 (`IRQ_F2P`) as
  well as ZynqMP, and for Xilinx cores (`ip2intc_irpt`) as well as ADI ones.
  A core with several interrupt outputs is left unresolved.

### Fixed

- Versal device trees now boot. The base tree named the wrong interrupt
  controller, left the system memory node unmarked, and enabled nodes that
  belong to the platform firmware and the RPU (IPI mailboxes, TMR cores, the
  RPU GIC and the ITS). Found by booting the generated AD9081 tree on a
  VPK180.
- A device node whose child shares a unit address with a base-tree node (such
  as `channel@1` and `cpus-r5@1`) no longer deletes that base node.
- AD9081 link mode 26 emitted `FDDC_I`/`FDDC_Q` macros without the header
  that defines them.
- Generated trees now boot the HDL 2026.1 designs on the 6.12 kernel
  (confirmed on the ZC706 ADRV9009, ZC706 ADRV9371 and ZCU102 AD9081 rigs):
  the ZC706 Ethernet PHY is declared, the SMMU that `sdtgen` enables is left
  disabled so PL DMA writes are not blocked, ADRV9009 clock generators list
  `clkin1` first, cache-coherent DMA cores carry `dma-coherent`, data offload
  cores are bound to their driver, and the AD9081 TX crossbar references its
  channels by label instead of fixed phandle numbers.
- AD9081 link-mode inference returned the wrong modes for M=8/L=4 and
  M=4/L=8; it now follows the kernel reference device trees (RX 10 / TX 9 and
  RX 18 / TX 17) and covers every framing they use.
- The linter no longer reports nested channel nodes as duplicate SPI chip
  selects, and no longer demands a `compatible` on nodes a parent device's
  driver owns (converter sub-nodes, Ethernet PHYs).
- The merger placed interrupt properties copied from an included stub after
  the node's sub-nodes, which `dtc` rejects.

## [0.1.0] - 2026-11-10

First public release. The `0.0.1` version number was used internally while
the release process was built out but was never tagged or published; its
content is folded into this entry.

### Added

- ADRV9040 standard RX/TX and ORX/NLS device models and ZCU102 XSA profiles,
  with pinned ADI Linux property parity, external-firmware documentation, and
  runnable examples. Hardware boot and RF qualification remain pending.
- Shared feature-driven MxFE core for AD9081/AD9084 with typed converter sides.
- Runtime/development requirements files and clean `[xsa]` wheel-install checks;
  PyPI metadata validation rejects direct URL requirements, including extras.
- Device-centric Python API for composing ADI converters, clocks, transceivers,
  evaluation boards, FPGA platforms, SPI connections, and JESD204 links.
- XSA-to-DTS pipeline with board profiles, structural validation, reference-DTS
  comparison, PetaLinux output, and interactive visualization reports.
- `adidtc` command-line workflows for XSA conversion, declarative DTS
  generation, Kuiper board discovery, live-tree inspection, and pyadi-jif clock
  updates.
- Versioned `adi.jif-dt` consumer contract and executable pyadi-jif handoff
  examples.
- Model Context Protocol server through the optional `mcp` dependency extra.
- ADRV9003 (Navassa) transceiver device and XSA builder with ZC706 and ZCU102
  profiles. Profiles must supply the ADRV9003 stream/profile inputs described
  in the XSA documentation.
- ADRV9009-ZU11EG / ADRV2CRR-FMC support: dual-radio SoM and carrier HMC7044
  clock tree, 245.76 MSPS reference profile, and a generated-DTB RAM boot test
  driven through production JTAG bootstrap with a checksummed serial transfer.
- AD9371 profile parsing aligned with the pyadi-jif model, observation-path
  wiring, alternate-profile coverage, and canonical ADRV9009 profile examples.
- Hardware CI coverage for AD9081/ZCU102, ADRV9009/ZC706, ADRV9371/ZC706,
  FMCDAQ3/VCU118, ADRV9009-ZU11EG/ADRV2CRR-FMC, and ADRV9361-Z7035/ADRV1CRR-FMC
  labgrid targets. The ADRV9361-Z7035 leg validates the booted stock device
  tree only; the package has no AD9361 model yet.
- Runtime overlay validation with configurable reload cycles, JESD and DMA
  checks on every cycle, and a reproducible modular test-kernel build.
- Pure-Python wheel and source distribution, Kuiper/Ubuntu Debian packages for
  amd64, arm64, and armhf, and native Debian 12, Fedora 42, and macOS 15
  system packages.
- Release workflow with preflight validation, SHA-256 asset manifests,
  non-publishing dry runs, PyPI trusted publishing, and an operator runbook.
- `adidtc` agent skill (`skills/pyadi-dt-cli`) and its Sphinx reference.
- `--hostname` option for the labgrid-exporter installer so exported resources
  advertise a name that resolves from the CI runners.

### Changed

- Git-only lab dependencies live in source requirements files rather than
  published extras. Hardware runners explicitly install
  `requirements/requirements_hw.txt`; public development installs use
  `requirements_dev.txt`.
- CodeQL analysis explicitly targets Python and GitHub Actions; vendored
  binding headers are data fixtures, not C/C++ build targets.
- Package and deployment name is `pyadi-dt` (import name remains `adidt`).
- Python 3.14 is supported; the supported range is 3.10 through 3.14.
- Kuiper test container images are pulled from the ADI Cloudsmith registry
  instead of a private Docker Hub repository.
- Hardware CI resolves `sdtgen`, Vitis, and `usbsdmux` tool paths explicitly,
  pins the labgrid plugin revision, and prepares checksum-verified DataX
  `adi-linux` kernel artifacts before acquiring boards. The manifest revision
  and CIM executable are pinned, and public dependency installation requires
  no private repository credentials.

### Fixed

- Use modular JESD clients for AD9081 runtime overlays and support
  ZynqMP overlay-kernel and module-bundle builds.
- Apply the JESD teardown patch reliably on fresh and repeated kernel builds.
- Connect the serial console before stock JTAG/SD autoboot starts.
- Allow a bounded 120 seconds for full kernel-log reads over busy serial
  transports, preserving complete diagnostics instead of timing out mid-log.
- Retry overlay-module downloads while networking becomes available after boot,
  and verify the bundle checksum before extraction.
- Publish generated DTBs and kernel overrides through the current labgrid
  artifact handoff, render the SD storage driver, and select a reachable
  management interface for the test TFTP server.
- Insert generated FPGA nodes at the actual AXI bus closing brace, preserving
  nested peripherals, and resolve SDTGen's `gic_a53` interrupt controller.
- Restore both PetaLinux pipeline entry points and target the ZynqMP GIC label.
- Preserve implicit and explicit JESD framing across raw/typed configurations,
  including auto-detected ADRV9040 and partial ORX overrides.
- Read real DTS/DTB files through MCP using the supported tree interface,
  full paths and compatible-string lookup.
- Fail checksum refresh on release-asset download errors, queue all tag
  publication workflows without cancellation, and propagate type/security
  checker failures through log capture.
- Correct clock/MxFE generic model types without suppressing diagnostics.
- Preserve ZynqMP DDR banks when removing duplicate SDT CPU metadata, including
  64-bit memory ranges and R5 aliases.
- Correct ZU11EG SoM/carrier HMC7044 wiring, unique output names, the dual-radio
  JESD graph, SPI chip selects, transport bindings, IIO names, Ethernet
  references and SD DMA configuration, preserving all four CPUs.
- Select ADRV9009-family DMA engines deterministically so an unrelated audio
  DMA cannot be wired to the radio in mixed-peripheral XSAs.
- Pace BootFabric serial writes to prevent command truncation on UART Lite.
- Complete AD9371/ZC706 System-API reference wiring and replace four unconditional
  expected failures with executable parity checks; add a real generated-DTB boot test.
- Provision runtime artifacts through per-board runner configuration and serve
  local module bundles only during overlay tests, with SHA256 verification.
- Initialize FMCDAQ3 TX before RX so shared clock synchronization completes
  before the ADC starts its link. Preserve overlay fault checks when the kernel
  message ring wraps.
- Stage only wheels and source distributions for PyPI publication, keeping
  checksum manifests with GitHub release assets.
- Return nonzero CLI exit codes for dependency-parser failures and unknown
  XSA profiles, with diagnostics on stderr.
- Reject hardware jobs with no passing tests and generated-DTB tests whose
  boot strategy ignores the staged device tree.
- Match FMCDAQ3 overlay tests to the coordinator's `daq3` feature so they no
  longer silently skip on the VCU118 place.
- Render TFTP hardware environments from live place tags, disable SD autoboot
  for generated-tree tests, and open serial before JTAG bootstrap. Reboot each
  deployment and verify a unique DTB marker in Linux to reject stale trees.
- Keep the place's own SD autoboot for boards whose U-Boot cannot use the
  TFTP kernel path (ADRV9361-Z7035), and skip the OS-reboot recovery test on
  any board the strategy JTAG-bootstraps rather than only on JTAG-named
  strategies.
- Discover the board IP address by walking every IPv4 default route and
  trying each address, instead of aborting when a board with two wired NICs
  (ADRV9361-Z7035 SoM plus ADRV1CRR-FMC carrier) holds two DHCP leases.
- Allow external XSA fixtures and private exporter-side fabric kernel images
  for hardware validation without replacing the shared stock boot image.
- Select the top-level HWH using the XSA manifest when scoped block-design
  handoffs occur earlier in the archive.
- Render FMCDAQ3 MicroBlaze bus clocks without an invalid `None` specifier.
- Emit the AD9371 observation DMA binding and reference interrupt, and give
  primary RX, observation, and TX distinct IIO node names on ZC706.
- Verify runtime overlay application through a unique live-tree property,
  preserving base symbols and checking removal. Configfs write success and
  `applied` status alone can hide kernel failures.
- Prepare overlay bases without duplicate SPI phandles, quiesce IIO clients,
  and reload the JESD topology around runtime changes. Supply an ADI 6.1.70
  JESD204 lifetime patch for the test kernel.
- Stage kernel overrides under the filename requested by U-Boot, and retain
  staged paths until the boot strategy consumes them. Select runtime kernels
  independently of ordinary boot tests in mixed hardware jobs.
- Remove duplicate AD9371/ADRV9009 overlay property updates and DMA fragments.
- Correct FMCDAQ3 clock selectors, output dividers and electrical modes,
  carrier GPIOs, SYSREF topology/settings, and ADC optimization registers.
  Honor AD9528 channel driver-mode settings in emitted bindings.
- Correct the PyPI publisher project name and distinguish historical hardware
  coverage from current release evidence.

### Known limitations

- The public API remains alpha and may change before a stable 1.0 release.
- XSA support requires Lopper/SDTGen and board-specific profiles.
- PetaLinux and hardware workflows depend on external AMD/ADI toolchains and
  lab resources that are not installed by the core Python package.
- Debian artifacts are thin packages: Python runtime dependencies listed in
  `pyproject.toml` must be supplied separately. They are not standalone
  application bundles.
- AD9081 has no generated-tree hardware qualification in the release evidence.
  Runtime overlay reload is qualified for 20 cycles followed by a reboot;
  unlimited cycling is not.

[Unreleased]: https://github.com/analogdevicesinc/pyadi-dt/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/analogdevicesinc/pyadi-dt/releases/tag/v0.1.0
