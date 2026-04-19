# Coordinator Support for Hardware Tests

## Summary

Enhance the hardware test infrastructure to support labgrid coordinator-based
target discovery alongside the existing direct `LG_ENV` path. The coordinator
address and exporter configuration are set via a `.env` file at the project
root, loaded automatically by `pytest-dotenv`.

## Motivation

The current hardware tests require a local labgrid environment YAML (`LG_ENV`)
pointing directly at target hardware. Moving to a coordinator allows
centralized resource management, place-based acquisition, and multiple exporter
modes — while keeping the direct path for Jenkins and local setups.

## Design

### Mode Detection

`test/hw/conftest.py` detects the active mode at fixture time:

1. `LG_COORDINATOR` set → **coordinator mode**
2. `LG_ENV` set → **direct mode** (current behavior, unchanged)
3. Neither set → skip all hardware tests

Within coordinator mode, three sub-modes are supported based on additional
environment variables (matching the labgrid-plugins convention):

| Sub-mode | Trigger | Behavior |
|----------|---------|----------|
| Discovery | `LG_COORDINATOR` only | Exporter already running; acquire published places |
| Single-spawn | `LG_EXPORTER_HOST` + `LG_EXPORTER_NAME` + `LG_EXPORTER_YAML` | Test session starts one exporter, tears it down at end |
| Multi-spawn | `LG_EXPORTERS_CONFIG` | Test session starts exporters per config, tears down at end |

### Environment Variables

All variables are optional. `.env` at project root is loaded by `pytest-dotenv`.

| Variable | Purpose | Example |
|----------|---------|---------|
| `LG_COORDINATOR` | Coordinator host:port | `10.0.0.41:20408` |
| `LG_EXPORTER_HOST` | Single-spawn: target hostname | `mini2` |
| `LG_EXPORTER_NAME` | Single-spawn: exporter name | `mini2` |
| `LG_EXPORTER_YAML` | Single-spawn: exporter resource YAML | `examples/lg_exporter.yaml` |
| `LG_EXPORTERS_CONFIG` | Multi-spawn: exporters config YAML | `tests/coordinator/exporters_all.yaml` |
| `LG_ENV` | Direct mode: labgrid env YAML path | `/jenkins/lg_ad9081_zcu102.yaml` |
| `ADI_XSA_BUILD_KERNEL` | Control kernel building (existing) | `1` |

### `.env.example`

A committed template at the project root with all supported variables
commented out and documented. `.env` is already in `.gitignore`.

### conftest.py Changes

The updated `test/hw/conftest.py`:

1. Reads `LG_COORDINATOR` and `LG_ENV` from the environment (already loaded
   by `pytest-dotenv`).
2. If `LG_COORDINATOR` is set:
   - Imports the `remote_exporters` fixture from the labgrid-plugins
     coordinator conftest (or reimplements the mode-detection logic inline
     if import is not feasible).
   - Provides a session-scoped `coordinator_target` fixture that acquires
     the place and returns a labgrid `Target`.
   - Derives `strategy` from the coordinator target.
3. If `LG_ENV` is set:
   - Existing behavior — labgrid pytest plugin provides `env` / `target` /
     `strategy`.
4. The `board` fixture (module-scoped) wraps `strategy` as it does today.
   Downstream code (`deploy_and_boot`, `collect_dmesg`, etc.) is unchanged.

### Test File Changes

Only the module-level skip guards change in each hardware test file:

```python
# Before
if not os.environ.get("LG_ENV"):
    pytest.skip(...)

# After
if not (os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV")):
    pytest.skip(...)
```

Test functions, `hw_helpers.py`, and all assertions are untouched.

### pyproject.toml Changes

- Add `pytest-dotenv` to the `test` optional dependency group.
- Add `env_files = .env` to `[tool.pytest.ini_options]`.
- Ensure `adi-labgrid-plugins` version supports coordinator features.

## Files Touched

| File | Change |
|------|--------|
| `test/hw/conftest.py` | Dual-path mode detection, coordinator fixtures |
| `test/hw/test_ad9081_zcu102_system_hw.py` | Skip guard: accept `LG_COORDINATOR` or `LG_ENV` |
| `test/hw/test_adrv9009_zcu102_hw.py` | Skip guard: accept `LG_COORDINATOR` or `LG_ENV` |
| `pyproject.toml` | Add `pytest-dotenv`, `env_files` config |
| `.env.example` | New — template with all supported variables |

## Out of Scope

- Writing exporter YAML files for specific boards (those are per-lab config).
- Writing labgrid env YAML files for coordinator places (paired with exporters).
- Coordinator Docker deployment (documented in labgrid-plugins).
- Changes to `hw_helpers.py` or test assertions.
