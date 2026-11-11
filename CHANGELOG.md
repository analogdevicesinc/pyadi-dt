# Changelog

All notable changes to pyadi-dt are documented here. The project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
