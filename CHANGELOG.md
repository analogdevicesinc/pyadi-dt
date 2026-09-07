# Changelog

All notable changes to pyadi-dt are documented here. The project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Preserve ZynqMP DDR banks when removing duplicate SDT CPU metadata, including
  64-bit memory ranges and R5 aliases.
- Correct ZU11EG SoM/carrier HMC7044 wiring, unique output names, the dual-radio
  JESD graph and 245.76 MSPS reference profile, SPI chip selects, transport
  bindings, IIO names, Ethernet references and SD DMA configuration. Add a
  generated-DTB RAM boot test using production JTAG bootstrap and a checksummed
  serial transfer, preserving all four CPUs.
- Select ADRV9009-family DMA engines deterministically so an unrelated audio
  DMA cannot be wired to the radio in mixed-peripheral XSAs.
- Exercise configurable overlay reload cycles with JESD and DMA checks on
  every cycle; pace BootFabric serial writes to prevent command truncation.
- Allow non-publishing release dry runs from committed candidate branches.

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
  and reload the JESD topology around runtime changes. Supply a reproducible
  modular test-kernel build and ADI 6.1.70 lifetime patch.
- Stage kernel overrides under the filename requested by U-Boot, and retain
  staged paths until the boot strategy consumes them. Select runtime kernels
  independently of ordinary boot tests in mixed hardware jobs.
- Remove duplicate AD9371/ADRV9009 overlay property updates and DMA fragments.
- Correct FMCDAQ3 clock selectors, output dividers and electrical modes,
  carrier GPIOs, SYSREF topology/settings, and ADC optimization registers.
  Honor AD9528 channel driver-mode settings in emitted bindings.
- Correct the PyPI publisher project name and distinguish historical hardware
  coverage from current release evidence.

## [0.0.1] - 2026-07-23

First public alpha release.

### Added

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
- Hardware CI coverage for AD9081/ZCU102, ADRV9009/ZC706,
  ADRV9371/ZC706, and FMCDAQ3/VCU118 labgrid targets.
- Pure-Python wheel, source distribution, and Debian packaging for amd64,
  arm64, and armhf.

### Known limitations

- The public API remains alpha and may change before a stable 1.0 release.
- XSA support requires Lopper/SDTGen and board-specific profiles.
- PetaLinux and hardware workflows depend on external AMD/ADI toolchains and
  lab resources that are not installed by the core Python package.
- Debian artifacts are thin packages: Python runtime dependencies listed in
  `pyproject.toml` must be supplied separately. They are not standalone
  application bundles.

[Unreleased]: https://github.com/analogdevicesinc/pyadi-dt/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/analogdevicesinc/pyadi-dt/releases/tag/v0.0.1
