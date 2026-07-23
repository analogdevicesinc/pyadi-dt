# Changelog

All notable changes to pyadi-dt are documented here. The project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
