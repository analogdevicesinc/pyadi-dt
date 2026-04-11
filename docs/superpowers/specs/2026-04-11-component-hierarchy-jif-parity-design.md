# Component Class Hierarchy & JIF Parity Design

## Goal

Restructure `adidt/model/` to use typed base classes per component role, split the monolithic `contexts.py` by device category, achieve parity with pyadi-jif's supported devices, and provide factories for all existing templates.

## Problem

1. **Flat component model** — `ComponentModel` is a single dataclass with a `role` string. No shared validation or defaults per device category. Every factory is a standalone function with no inherited structure.

2. **Monolithic contexts.py** — 19 builder functions in one ~1000-line file. Adding more devices makes this unwieldy.

3. **JIF parity gaps** — pyadi-jif supports AD9082, AD9088, ADRV9009, LTC6952, LTC6953, AD9545 but adidt has no `ComponentModel` factories for them.

4. **Orphan templates** — 17 Jinja2 templates (admv1013, adf4371, ad9467, etc.) exist with no corresponding factory or context builder.

## Architecture

### Three-Layer Design

```
Component Classes (adidt/model/components/)
    typed base classes per role, classmethods as factories
         │
         ▼
Context Builders (adidt/model/contexts/)
    split by category: clocks.py, converters.py, transceivers.py, sensors.py, fpga.py
         │
         ▼
Jinja2 Templates (adidt/templates/xsa/)
    one .tmpl per device, rendered by BoardModelRenderer
```

### Component Class Hierarchy

`ComponentModel` remains the core dataclass (unchanged for backward compatibility). New base classes inherit from it and add role-specific defaults, validation, and factory classmethods.

```
ComponentModel (dataclass — fields: role, part, template, spi_bus, spi_cs, config)
│
├── ClockComponent(ComponentModel)
│   role = "clock"
│   Validates: channel configs, vcxo frequency
│   Factories:
│     .hmc7044(spi_bus, cs, *, channels, vcxo, ...)       # jif-supported
│     .ad9523_1(spi_bus, cs, *, channels, vcxo, ...)      # jif-supported
│     .ad9528(spi_bus, cs, *, channels, vcxo, ...)        # jif-supported
│     .ad9545(spi_bus, cs, *, dpll_configs, ...)           # jif-supported (NEW)
│     .ltc6952(spi_bus, cs, *, channels, ...)              # jif-supported (NEW)
│     .ltc6953(spi_bus, cs, *, channels, ...)              # jif-supported (NEW)
│     .adf4371(spi_bus, cs, *, config)                     # template-only
│     .adf4377(spi_bus, cs, *, config)                     # template-only
│     .adf4382(spi_bus, cs, *, config)                     # existing context
│     .adf4350(spi_bus, cs, *, config)                     # template-only
│     .adf4030(spi_bus, cs, *, config)                     # template-only
│
├── AdcComponent(ComponentModel)
│   role = "adc"
│   Validates: JESD link params (F, K, M, L, Np, S) when present
│   Factories:
│     .ad9680(spi_bus, cs, *, jesd_params, ...)            # jif-supported
│     .ad9088(spi_bus, cs, *, jesd_params, ...)            # jif-supported (NEW)
│     .ad9467(spi_bus, cs, *, config)                      # template-only
│     .ad7768(spi_bus, cs, *, config)                      # template-only
│     .adaq8092(spi_bus, cs, *, config)                    # template-only
│     .ad7124(spi_bus, cs, *, config)                      # existing (no JESD)
│
├── DacComponent(ComponentModel)
│   role = "dac"
│   Validates: JESD link params when present
│   Factories:
│     .ad9144(spi_bus, cs, *, jesd_params, ...)            # jif-supported
│     .ad9152(spi_bus, cs, *, jesd_params, ...)            # jif-supported
│     .ad9172(spi_bus, cs, *, jesd_params, ...)            # existing
│     .ad9739a(spi_bus, cs, *, config)                     # template-only
│     .ad916x(spi_bus, cs, *, config)                      # template-only
│
├── TransceiverComponent(ComponentModel)
│   role = "transceiver"
│   Validates: RX + TX JESD params
│   Factories:
│     .ad9081(spi_bus, cs, *, rx_jesd, tx_jesd, ...)       # jif-supported
│     .ad9082(spi_bus, cs, *, rx_jesd, tx_jesd, ...)       # jif-supported (NEW)
│     .ad9084(spi_bus, cs, *, rx_jesd, ...)                # jif-supported
│     .adrv9009(spi_bus, cs, *, rx_jesd, tx_jesd, ...)     # jif-supported (NEW factory)
│     .ad9083(spi_bus, cs, *, config)                      # template-only
│
├── SensorComponent(ComponentModel)
│   role = "sensor"
│   Defaults: simple SPI, no JESD
│   Factories:
│     .adis16495(spi_bus, cs, *, interrupt_gpio, ...)      # existing
│     .adxl345(spi_bus, cs, *, interrupt_gpio, ...)        # existing
│
└── RfFrontendComponent(ComponentModel)
    role = "rf_frontend"
    Defaults: SPI device, no JESD
    Factories:
      .admv1013(spi_bus, cs, *, config)                    # template-only
      .admv1014(spi_bus, cs, *, config)                    # template-only
      .adrf6780(spi_bus, cs, *, config)                    # template-only
      .adar1000(spi_bus, cs, *, config)                    # template-only
```

### Base Class Responsibilities

**All base classes provide:**
- Default `role` value (no need to pass it)
- `__init_subclass__` or `__post_init__` validation
- A `from_config(spi_bus, cs, config)` generic classmethod for manual/template-only devices

**JesdDeviceMixin** (shared by AdcComponent, DacComponent, TransceiverComponent):
- Validates JESD link parameters when present in config
- Normalizes JESD subclass names ("jesd204b" -> 1)
- Shared constants for JESD parameter bounds

**ClockComponent specifically:**
- Validates channel divider configs
- Validates vcxo frequency is an integer

### Context Builder Split

Current single file `adidt/model/contexts.py` splits into:

```
adidt/model/contexts/
├── __init__.py        # Re-exports ALL builders for backward compat:
│                      #   from .clocks import *
│                      #   from .converters import *
│                      #   etc.
├── clocks.py          # build_hmc7044_ctx, build_hmc7044_channel_ctx,
│                      # build_ad9523_1_ctx, build_ad9528_ctx, build_ad9528_1_ctx,
│                      # build_adf4382_ctx
│                      # NEW: build_ad9545_ctx, build_ltc6952_ctx, build_ltc6953_ctx,
│                      #      build_adf4371_ctx, build_adf4377_ctx, build_adf4350_ctx,
│                      #      build_adf4030_ctx
├── converters.py      # build_ad9680_ctx, build_ad9144_ctx, build_ad9152_ctx,
│                      # build_ad9172_device_ctx
│                      # NEW: build_ad9088_ctx, build_ad9467_ctx, build_ad7768_ctx,
│                      #      build_adaq8092_ctx, build_ad9739a_ctx, build_ad916x_ctx
├── transceivers.py    # build_ad9081_mxfe_ctx, build_ad9084_ctx,
│                      # build_adrv9009_device_ctx
│                      # NEW: build_ad9082_ctx, build_ad9083_ctx
├── sensors.py         # build_adis16495_ctx, build_adxl345_ctx, build_ad7124_ctx
├── rf_frontends.py    # NEW: build_admv1013_ctx, build_admv1014_ctx,
│                      #      build_adrf6780_ctx, build_adar1000_ctx
└── fpga.py            # build_adxcvr_ctx, build_jesd204_overlay_ctx,
                       # build_tpl_core_ctx
                       # Also: fmt_hz, coerce_board_int utilities
```

### New Devices for JIF Parity

These devices have pyadi-jif solver support but no adidt factory:

| Device | Type | What Exists | What to Add |
|--------|------|-------------|-------------|
| AD9082 | Transceiver | Template (via ad9081) | Factory + context (reuses ad9081 context with mode flag) |
| AD9088 | ADC | Template (ad9088.tmpl) | Factory + context |
| ADRV9009 | Transceiver | Context exists, no factory | Factory wrapping existing context |
| LTC6952 | Clock | Template (ltc6952.tmpl) | Factory + context |
| LTC6953 | Clock | No template | Template + factory + context |
| AD9545 | Clock | Template + parts class | Factory + context (bridge from parts class) |

### Template-Only Devices

These devices have Jinja2 templates but no jif solver. They get minimal factories that accept a raw config dict:

| Device | Type | Template |
|--------|------|----------|
| ADF4371 | Clock | adf4371.tmpl |
| ADF4377 | Clock | adf4377.tmpl |
| ADF4350 | Clock | adf4350.tmpl |
| ADF4030 | Clock | adf4030.tmpl |
| AD9467 | ADC | ad9467.tmpl |
| AD7768 | ADC | ad7768.tmpl |
| ADAQ8092 | ADC | adaq8092.tmpl |
| AD9739A | DAC | ad9739a.tmpl |
| AD916x | DAC | ad916x.tmpl |
| AD9083 | Transceiver | ad9083.tmpl |
| ADMV1013 | RF Frontend | admv1013.tmpl |
| ADMV1014 | RF Frontend | admv1014.tmpl |
| ADRF6780 | RF Frontend | adrf6780.tmpl |
| ADAR1000 | RF Frontend | adar1000.tmpl |

Template-only factory signature: `.device_name(spi_bus, cs, *, config: dict)` where `config` is passed through as-is to the template.

### File Structure

```
adidt/model/
├── __init__.py           # Unchanged exports
├── board_model.py        # ComponentModel stays here (unchanged)
├── renderer.py           # Unchanged
├── components/
│   ├── __init__.py       # Re-exports: ClockComponent, AdcComponent, etc.
│   │                     # Also backward-compat standalone functions
│   ├── base.py           # JesdDeviceMixin, shared validation
│   ├── clocks.py         # ClockComponent class + all clock factories
│   ├── converters.py     # AdcComponent, DacComponent + factories
│   ├── transceivers.py   # TransceiverComponent + factories
│   ├── sensors.py        # SensorComponent + factories
│   └── rf_frontends.py   # RfFrontendComponent + factories
└── contexts/
    ├── __init__.py       # Re-exports all builders
    ├── clocks.py
    ├── converters.py
    ├── transceivers.py
    ├── sensors.py
    ├── rf_frontends.py
    └── fpga.py
```

### Backward Compatibility

1. **`from adidt.model.contexts import build_hmc7044_ctx`** — still works via `__init__.py` re-exports
2. **`from adidt.model import components; components.ad9680(...)`** — still works, standalone functions delegate to classmethods
3. **`ComponentModel` dataclass** — unchanged, all new classes inherit from it
4. **Board classes** — no changes needed, they construct ComponentModel instances directly
5. **BoardModelRenderer** — unchanged, it consumes ComponentModel which the new classes are

### New Template

One new template needed:

- `adidt/templates/xsa/ltc6953.tmpl` — LTC6953 clock distributor (no template exists today)

All other devices already have templates.

### Testing Strategy

- **Unit tests per component class** — Verify each factory produces correct ComponentModel with right role, part, template, config
- **Validation tests** — Verify base class validation catches bad inputs (invalid JESD params, non-integer vcxo, etc.)
- **Backward compat tests** — Verify old import paths and standalone functions still work
- **Render tests** — Verify each new factory's output renders through BoardModelRenderer without errors
- **Context split tests** — Verify all existing context builders still produce identical output after the split

### Documentation

- Google-style docstrings on all new classes and methods
- Module-level docstrings on each new file explaining its scope
- Docstrings enforced by ruff only in `adidt/xsa/` per existing convention, but we add them to `adidt/model/` voluntarily for clarity

## Out of Scope

- Changes to board classes (they consume ComponentModel and don't need changes)
- Changes to parts/ classes (they serve a different purpose: runtime DT manipulation)
- Changes to XSA pipeline/builders (they construct ComponentModel directly)
- Changes to BoardModelRenderer (it consumes ComponentModel generically)
- Adding new board classes for new devices
