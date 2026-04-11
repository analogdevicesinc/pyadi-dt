# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

pyadi-dt (package name `adidt`) is a device tree generation and management library for Analog Devices hardware. It provides an XSA-to-DTS pipeline (Vivado → device tree source), a BoardModel API for programmatic device tree construction, and a Click CLI (`adidtc`). Supports 88+ Kuiper Linux boards. Also exposes functionality via a FastMCP server (`adidt-mcp`).

## Commands

```bash
# Testing
nox -s tests                              # Run full test suite (Python 3.10)
nox -s tests -- test/xsa/ -v -k "ad9081"  # Run specific tests with filters
pytest -vs test/test_dt.py                 # Run a single test file directly
pytest -vs test/test_dt.py::test_func      # Run a single test function

# Linting & formatting
nox -s lint                  # Ruff linter (adidt + test)
nox -s format                # Ruff auto-format
nox -s format_check          # Check formatting without modifying

# Type checking
nox -s ty                    # Type check model/, boards/, xsa/builders/ with ty
nox -s ty -- adidt/model/    # Check specific module

# Docs
nox -s docs                  # Build Sphinx docs
nox -s docs_serve            # Live preview with autobuild

# Specialized test sessions
nox -s dts_lint              # DTS structural linter tests
nox -s dtc_compile           # DTS syntax validation (requires dtc on PATH)
nox -s coverage              # pytest with coverage report
nox -s security_audit        # pip-audit for dependency vulnerabilities
nox -s bandit                # Bandit security linter against source

# Build
nox -s build                 # Build sdist + wheel
```

Nox uses `uv` as its venv backend.

## Architecture

```
adidt/
├── cli/              Click CLI ("adidtc") — commands: xsa2dt, gen-dts, profile2dt, kuiper-boards, prop, props, deps
├── model/            BoardModel API — programmatic device tree construction
│   ├── board_model.py   Core BoardModel class
│   ├── components.py    Pre-configured device factories
│   ├── contexts.py      Context managers for tree building
│   └── renderer.py      DTS output renderer
├── boards/           Board classes for each supported platform (daq2, ad9081, adrv9009, rpi, etc.)
├── parts/            Clock/converter driver configurations (ad9523_1, ad9545, hmc7044, adrv9009)
├── xsa/              XSA pipeline — heaviest subsystem
│   ├── pipeline.py      XSA processing pipeline
│   ├── profiles.py      Board profiles manager (JSON in xsa/profiles/)
│   ├── kuiper.py        Kuiper board manifest
│   ├── topology.py      Clock/topology analysis
│   ├── dts_lint.py      DTS linting & validation
│   ├── petalinux.py     PetaLinux integration
│   └── builders/        Device-specific DTS builders
├── templates/        Jinja2 templates for DTS generation
├── mcp_server.py     FastMCP server exposing device tree generation to AI tools
├── clock.py          Clock tree handling
├── dt.py             Device tree utilities
└── sd.py             SD card deployment
```

**Data flow:** XSA file → Vivado sdtgen → raw device tree → BoardModel/pipeline processing → DTS/DTSI output → optional DTS lint + D2 diagram reports.

## Key Conventions

- **Ruff**: Google-style docstrings enforced only in `adidt/xsa/**` (all other paths exempt from D rules). Standard E/W/F/I/UP/B/SIM rules not explicitly configured beyond docstrings.
- **Type checking**: `ty` targets `adidt/model/`, `adidt/boards/`, `adidt/xsa/builders/` — unresolved-import rule is set to ignore (missing third-party stubs).
- **Test exclusions**: `test/hw/` and `*_hw.py` files are excluded by default (require physical hardware). Marker `network` for internet-dependent tests.
- **Package data**: Jinja2 templates (`*.tmpl`), XSA profiles (`*.json`), D3 bundle, and static assets are included in the distribution.
- **Python**: 3.10+ required.

## Integration Points

- **pyd2lang-native**: Used in `nox -s d2_diagrams` to compile D2 diagram sources to SVG for documentation.
- **FastMCP**: `adidt-mcp` entry point exposes device tree generation via MCP protocol.
- **PetaLinux**: Full build integration via `nox -s petalinux_build` (requires PetaLinux tools + XSA file via env vars).
