# XSA Full Devicetree Mapping Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a reference-driven XSA->SDTGen->full-DTS pipeline that achieves structural parity against the ADI AD9081+ZCU102 reference tree and validates output in both existing and dedicated hardware test paths.

**Architecture:** Add a manifest extraction layer (`adidt/xsa/reference`) and a mapping layer (`adidt/xsa/mapping`) between current topology parsing and merge output. The mapper resolves required driver roles and links from XSA/SDTGen/pyadi-jif sources, emits parity artifacts, and gates generation on required-role coverage. Vendor selected `pyadi-build` helpers under `adidt/build/` and wire both legacy and dedicated hardware tests to generated DTB artifacts.

**Tech Stack:** Python 3.12, pytest, click, jinja2, dtc, SDTGen/lopper, Vivado XSA, pyadi-jif JSON config, vendored pyadi-build helpers.

---

## File Structure Map

- Create: `adidt/xsa/reference/schema.py`  
Responsibility: dataclasses for manifest roles, property/link requirements, multiplicity.

- Create: `adidt/xsa/reference/parser.py`  
Responsibility: parse root DTS + includes into `DriverManifest`.

- Create: `adidt/xsa/reference/__init__.py`  
Responsibility: public exports for reference layer.

- Create: `adidt/xsa/mapping/schema.py`  
Responsibility: mapping result dataclasses, reason enums, provenance tags.

- Create: `adidt/xsa/mapping/resolver.py`  
Responsibility: role resolution from topology + base DTS + pyadi-jif config.

- Create: `adidt/xsa/mapping/parity.py`  
Responsibility: enforce required-role/link/property coverage; produce failure/warning lists.

- Create: `adidt/xsa/mapping/__init__.py`  
Responsibility: public exports for mapping layer.

- Modify: `adidt/xsa/pipeline.py`  
Responsibility: invoke manifest parser + resolver + parity checker and emit `.map.json` + `.coverage.md`.

- Modify: `adidt/xsa/merger.py`  
Responsibility: preserve/insert resolved links and stable node insertion order for deterministic outputs.

- Create: `adidt/build/pyadi_build_vendor/__init__.py`  
Responsibility: vendored entrypoint exports.

- Create: `adidt/build/pyadi_build_vendor/build_runner.py`  
Responsibility: run build/stage routines copied from `tfcollins/pyadi-build`.

- Create: `adidt/build/adapter.py`  
Responsibility: thin wrapper API used by tests and CLI, isolating vendored internals.

- Modify: `adidt/cli/main.py`  
Responsibility: add options for reference DTS root path and Linux tree path; print parity summary.

- Create: `test/xsa/fixtures/reference/zynqmp-zcu102-rev10-ad9081-m8-l4.dts`  
Responsibility: local frozen root reference fixture.

- Create: `test/xsa/fixtures/reference/*.dtsi`  
Responsibility: local frozen include fixture set required by parser tests.

- Create: `test/xsa/test_reference_parser.py`  
Responsibility: tests for manifest extraction and include traversal.

- Create: `test/xsa/test_mapping_resolver.py`  
Responsibility: tests for role mapping + provenance and gap reasons.

- Create: `test/xsa/test_parity.py`  
Responsibility: tests for hard/soft parity decisions.

- Modify: `test/xsa/test_pipeline.py`  
Responsibility: e2e checks for new artifacts and parity gating behavior.

- Modify: `test/hw/test_ad9081_new.py`  
Responsibility: parameterize to accept generated DTB path.

- Modify: `test/hw/test_ad9081_multirate_hw.py`  
Responsibility: parameterize to accept generated DTB path.

- Create: `test/hw_xsa/__init__.py`  
Responsibility: package marker.

- Create: `test/hw_xsa/test_xsa_boot_smoke.py`  
Responsibility: dedicated boot/deploy smoke using generated DTB.

- Create: `test/hw_xsa/test_xsa_driver_bindings.py`  
Responsibility: verify expected key drivers bind with generated tree.

- Modify: `doc/source/examples/xsa_ad9081_zcu102.md`  
Responsibility: document full-reference path and test flow.

- Modify: `doc/source/xsa.rst`  
Responsibility: include new command options and parity artifact descriptions.

## Chunk 1: Reference Manifest Foundation

### Task 1: Add reference manifest schema

**Files:**
- Create: `adidt/xsa/reference/schema.py`
- Create: `adidt/xsa/reference/__init__.py`
- Test: `test/xsa/test_reference_parser.py`

- [ ] **Step 1: Write the failing schema test**

```python
# test/xsa/test_reference_parser.py
from adidt.xsa.reference.schema import ManifestRole


def test_manifest_role_defaults_required_single():
    role = ManifestRole(name="ad9081_core")
    assert role.optional is False
    assert role.multiplicity == "single"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test/xsa/test_reference_parser.py::test_manifest_role_defaults_required_single -v`  
Expected: FAIL with import/module not found for `adidt.xsa.reference`.

- [ ] **Step 3: Implement minimal schema/dataclasses**

```python
# adidt/xsa/reference/schema.py
from dataclasses import dataclass, field


@dataclass
class ManifestRole:
    name: str
    match_hints: dict[str, str] = field(default_factory=dict)
    required_properties: list[str] = field(default_factory=list)
    required_links: list[str] = field(default_factory=list)
    multiplicity: str = "single"
    optional: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test/xsa/test_reference_parser.py::test_manifest_role_defaults_required_single -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/reference/schema.py adidt/xsa/reference/__init__.py test/xsa/test_reference_parser.py
git commit -m "feat(xsa): add reference manifest schema dataclasses"
```

### Task 2: Parse root DTS + includes into DriverManifest

**Files:**
- Create: `adidt/xsa/reference/parser.py`
- Create: `test/xsa/fixtures/reference/zynqmp-zcu102-rev10-ad9081-m8-l4.dts`
- Create: `test/xsa/fixtures/reference/*.dtsi`
- Modify: `test/xsa/test_reference_parser.py`

- [ ] **Step 1: Write failing parser tests for include traversal and role extraction**

```python
# append in test/xsa/test_reference_parser.py
from pathlib import Path
from adidt.xsa.reference.parser import ReferenceManifestParser


def test_parser_follows_includes_and_extracts_roles():
    root = Path("test/xsa/fixtures/reference/zynqmp-zcu102-rev10-ad9081-m8-l4.dts")
    manifest = ReferenceManifestParser().parse(root)
    role_names = {r.name for r in manifest.roles}
    assert "ad9081_core" in role_names
    assert "jesd_rx_link" in role_names
    assert "jesd_tx_link" in role_names
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest test/xsa/test_reference_parser.py -v`  
Expected: FAIL with `ReferenceManifestParser` missing.

- [ ] **Step 3: Implement parser with deterministic include resolution**

```python
# parser skeleton behavior
# - load root text
# - parse #include "..." recursively (single directory tree rooted at fixture dir)
# - extract nodes with compatible + labels
# - map to canonical roles via role table
# - return DriverManifest(roles=[...])
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest test/xsa/test_reference_parser.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/reference/parser.py test/xsa/fixtures/reference test/xsa/test_reference_parser.py
git commit -m "feat(xsa): parse ADI reference dts include graph into driver manifest"
```

### Task 3: Verify Chunk 1

**Files:**
- Test: `test/xsa/test_reference_parser.py`

- [ ] **Step 1: Run full chunk test command**

Run: `pytest test/xsa/test_reference_parser.py -v`  
Expected: all tests PASS.

- [ ] **Step 2: Run style/lint command used in repo (if configured)**

Run: `nox -s tests -- test/xsa/test_reference_parser.py`  
Expected: session PASS or skip if nox env unavailable.

- [ ] **Step 3: Commit verification-only adjustments (if any)**

```bash
git add -A
git commit -m "test(xsa): stabilize reference parser tests and fixtures"
```

## Chunk 2: Mapping Engine and Parity Gates

### Task 4: Add mapping schema and gap reason enums

**Files:**
- Create: `adidt/xsa/mapping/schema.py`
- Create: `adidt/xsa/mapping/__init__.py`
- Create: `test/xsa/test_mapping_resolver.py`

- [ ] **Step 1: Write failing mapping schema tests**

```python
from adidt.xsa.mapping.schema import GapReason


def test_gap_reason_contains_required_values():
    assert GapReason.MISSING_IN_XSA.value == "missing_in_xsa"
    assert GapReason.UNSUPPORTED_ROLE.value == "unsupported_role"
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest test/xsa/test_mapping_resolver.py::test_gap_reason_contains_required_values -v`  
Expected: FAIL import error.

- [ ] **Step 3: Implement enum/dataclasses**

```python
from enum import Enum


class GapReason(str, Enum):
    MISSING_IN_XSA = "missing_in_xsa"
    MISSING_IN_SDTGEN = "missing_in_sdtgen"
    MISSING_IN_JIF = "missing_in_jif"
    UNSUPPORTED_ROLE = "unsupported_role"
```

- [ ] **Step 4: Run test to pass**

Run: `pytest test/xsa/test_mapping_resolver.py::test_gap_reason_contains_required_values -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/mapping/schema.py adidt/xsa/mapping/__init__.py test/xsa/test_mapping_resolver.py
git commit -m "feat(xsa): add mapping result schema and gap reason enums"
```

### Task 5: Implement role resolver from topology + base DTS + config

**Files:**
- Create: `adidt/xsa/mapping/resolver.py`
- Modify: `test/xsa/test_mapping_resolver.py`

- [ ] **Step 1: Write failing resolver tests for required roles and provenance**

```python
from adidt.xsa.mapping.resolver import RoleResolver


def test_resolver_maps_required_roles(ad9081_topology, ad9081_manifest, ad9081_cfg):
    result = RoleResolver().resolve(ad9081_topology, ad9081_manifest, ad9081_cfg, base_dts="/dts-v1/; / {};\n")
    assert "ad9081_core" in result.mapped_roles
    assert "jesd_rx_link" in result.mapped_roles
    assert not result.gaps
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest test/xsa/test_mapping_resolver.py -v -k resolver`  
Expected: FAIL (`RoleResolver` missing).

- [ ] **Step 3: Implement minimal resolver logic for AD9081+ZCU102 role pack**

```python
# RoleResolver.resolve(...)
# - index topology objects by ip_type/instance
# - choose node candidates from base DTS labels where needed
# - populate mapped role specs with source tags
# - append Gap(reason=...) for unresolved required role
```

- [ ] **Step 4: Run resolver tests to pass**

Run: `pytest test/xsa/test_mapping_resolver.py -v -k resolver`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/mapping/resolver.py test/xsa/test_mapping_resolver.py
git commit -m "feat(xsa): add AD9081 role resolver with provenance and gap reporting"
```

### Task 6: Add parity checker (hard fail for required gaps)

**Files:**
- Create: `adidt/xsa/mapping/parity.py`
- Create: `test/xsa/test_parity.py`

- [ ] **Step 1: Write failing parity tests for hard/soft conditions**

```python
from adidt.xsa.mapping.parity import check_parity


def test_parity_fails_when_required_role_missing(sample_mapping_result):
    report = check_parity(sample_mapping_result)
    assert report.ok is False
    assert "required role" in report.errors[0]
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest test/xsa/test_parity.py -v`  
Expected: FAIL (module missing).

- [ ] **Step 3: Implement parity checker**

```python
# check_parity(result)
# - errors for required-role gaps / required-link misses / required-prop misses
# - warnings for optional gaps/defaulted fields
# - return ParityReport(ok=..., errors=[...], warnings=[...])
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest test/xsa/test_parity.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/mapping/parity.py test/xsa/test_parity.py
git commit -m "feat(xsa): add structural parity checker with hard and soft gates"
```

### Task 7: Verify Chunk 2

**Files:**
- Test: `test/xsa/test_mapping_resolver.py`
- Test: `test/xsa/test_parity.py`

- [ ] **Step 1: Run combined mapping tests**

Run: `pytest test/xsa/test_mapping_resolver.py test/xsa/test_parity.py -v`  
Expected: all PASS.

- [ ] **Step 2: Re-run xsa pipeline baseline tests for regression safety**

Run: `pytest test/xsa/test_pipeline.py -v`  
Expected: PASS.

- [ ] **Step 3: Commit verification adjustments (if any)**

```bash
git add -A
git commit -m "test(xsa): verify mapping and parity integration with existing pipeline tests"
```

## Chunk 3: Pipeline, CLI, and pyadi-build Vendor Adapter

### Task 8: Wire resolver + parity artifacts into pipeline

**Files:**
- Modify: `adidt/xsa/pipeline.py`
- Modify: `test/xsa/test_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests for new output artifacts**

```python
def test_pipeline_writes_map_and_coverage(xsa_path, cfg, tmp_path):
    result = XsaPipeline().run(xsa_path, cfg, tmp_path, reference_dts_root=REF_ROOT)
    assert (tmp_path / "ad9081_zcu102.map.json").exists()
    assert (tmp_path / "ad9081_zcu102.coverage.md").exists()
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest test/xsa/test_pipeline.py -v -k map_and_coverage`  
Expected: FAIL (new params/artifacts absent).

- [ ] **Step 3: Implement pipeline integration**

```python
# XsaPipeline.run(..., reference_dts_root: Path | None = None)
# - parse manifest
# - resolve roles
# - parity check
# - fail fast on parity errors
# - write map.json and coverage.md
# - continue merge + report on parity success
```

- [ ] **Step 4: Run pipeline tests to pass**

Run: `pytest test/xsa/test_pipeline.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/xsa/pipeline.py test/xsa/test_pipeline.py
git commit -m "feat(xsa): add manifest-driven mapping and parity artifacts to pipeline"
```

### Task 9: Add vendored pyadi-build adapter

**Files:**
- Create: `adidt/build/pyadi_build_vendor/__init__.py`
- Create: `adidt/build/pyadi_build_vendor/build_runner.py`
- Create: `adidt/build/adapter.py`
- Create: `test/xsa/test_build_adapter.py`

- [ ] **Step 1: Write failing adapter tests for build and staging API**

```python
from adidt.build.adapter import BuildAdapter


def test_build_adapter_exposes_build_kernel_dtb():
    adapter = BuildAdapter()
    assert hasattr(adapter, "build_kernel_dtb")
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest test/xsa/test_build_adapter.py -v`  
Expected: FAIL import error.

- [ ] **Step 3: Vendor selected pyadi-build helpers and implement thin adapter**

```python
# adapter methods
# - build_kernel_dtb(...)
# - stage_boot_artifacts(...)
# - deploy_to_target(...)
# Each method delegates to vendored runner functions.
```

- [ ] **Step 4: Run adapter tests to pass**

Run: `pytest test/xsa/test_build_adapter.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/build/pyadi_build_vendor adidt/build/adapter.py test/xsa/test_build_adapter.py
git commit -m "feat(build): vendor pyadi-build helpers behind local adapter interface"
```

### Task 10: Extend CLI for reference-root and parity summary

**Files:**
- Modify: `adidt/cli/main.py`
- Modify: `test/xsa/test_pipeline.py`

- [ ] **Step 1: Write failing CLI test for new option plumbing**

```python
def test_xsa2dt_accepts_reference_root(cli_runner, tmp_paths):
    result = cli_runner.invoke(cli, ["xsa2dt", "-x", "design.xsa", "-c", "cfg.json", "--reference-dts-root", "ref/root.dts"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify fail**

Run: `pytest test/xsa/test_pipeline.py -v -k reference_root`  
Expected: FAIL (unknown option).

- [ ] **Step 3: Implement CLI option and parity summary output**

```python
@click.option("--reference-dts-root", type=click.Path(exists=True), default=None)
# pass to XsaPipeline.run(...)
# print parity summary counts: mapped / warnings / errors
```

- [ ] **Step 4: Run CLI-related tests to pass**

Run: `pytest test/xsa/test_pipeline.py -v -k "reference_root or xsa2dt"`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adidt/cli/main.py test/xsa/test_pipeline.py
git commit -m "feat(cli): add reference dts root input and parity summary for xsa2dt"
```

### Task 11: Verify Chunk 3

**Files:**
- Test: `test/xsa/test_pipeline.py`
- Test: `test/xsa/test_build_adapter.py`

- [ ] **Step 1: Run chunk-level integration tests**

Run: `pytest test/xsa/test_pipeline.py test/xsa/test_build_adapter.py -v`  
Expected: PASS.

- [ ] **Step 2: Run broader XSA suite for regressions**

Run: `pytest test/xsa -v`  
Expected: PASS (or documented pre-existing failures only).

- [ ] **Step 3: Commit verification adjustments (if any)**

```bash
git add -A
git commit -m "test(xsa): verify pipeline, cli, and build adapter integration"
```

## Chunk 4: Hardware Validation Paths and Documentation

### Task 12: Extend existing AD9081 hardware tests for generated DTB input

**Files:**
- Modify: `test/hw/test_ad9081_new.py`
- Modify: `test/hw/test_ad9081_multirate_hw.py`

- [ ] **Step 1: Write failing tests/fixtures for generated DTB parameter path**

```python
@pytest.mark.parametrize("dtb_source", ["reference", "generated_xsa"])
def test_ad9081_boot(dtb_source, ...):
    assert dtb_source in {"reference", "generated_xsa"}
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest test/hw/test_ad9081_new.py -v -k generated_xsa`  
Expected: FAIL (fixture/param path not present).

- [ ] **Step 3: Implement generated DTB artifact selection/deploy path**

```python
# reuse existing deploy helper
# when dtb_source == "generated_xsa":
#   use adapter-produced artifact path
# else: existing behavior
```

- [ ] **Step 4: Run tests to verify pass/skips**

Run: `pytest test/hw/test_ad9081_new.py test/hw/test_ad9081_multirate_hw.py -v -k generated_xsa`  
Expected: PASS or SKIP on unavailable hardware, no import/runtime errors.

- [ ] **Step 5: Commit**

```bash
git add test/hw/test_ad9081_new.py test/hw/test_ad9081_multirate_hw.py
git commit -m "test(hw): add generated xsa dtb path to existing ad9081 hardware tests"
```

### Task 13: Add dedicated XSA hardware smoke suite

**Files:**
- Create: `test/hw_xsa/__init__.py`
- Create: `test/hw_xsa/test_xsa_boot_smoke.py`
- Create: `test/hw_xsa/test_xsa_driver_bindings.py`

- [ ] **Step 1: Write failing smoke tests**

```python
def test_xsa_generated_dtb_boot_smoke(...):
    # boot with generated dtb
    assert boot_result.success


def test_xsa_expected_driver_bindings(...):
    # verify ad9081 + jesd core nodes bound
    assert "axi-jesd204-rx" in bindings
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest test/hw_xsa -v`  
Expected: FAIL (module/tests absent).

- [ ] **Step 3: Implement dedicated suite with reusable hw helpers**

```python
# test_xsa_boot_smoke.py
# - generate artifacts if needed
# - deploy dtb/bit/bin files
# - boot + smoke check

# test_xsa_driver_bindings.py
# - query target sysfs/devices
# - assert key drivers are present
```

- [ ] **Step 4: Run tests to verify pass/skips**

Run: `pytest test/hw_xsa -v`  
Expected: PASS or SKIP on unavailable hardware; no unexpected errors.

- [ ] **Step 5: Commit**

```bash
git add test/hw_xsa
git commit -m "test(hw_xsa): add dedicated generated-devicetree hardware smoke suite"
```

### Task 14: Add integration test using real SDTGen + example XSA when tools exist

**Files:**
- Modify: `test/xsa/test_pipeline.py`

- [ ] **Step 1: Write failing integration test guarded by tool availability**

```python
@pytest.mark.integration
def test_pipeline_with_real_sdtgen_and_example_xsa(tmp_path):
    # skip if sdtgen unavailable
    # run on examples/xsa/system_top.xsa
    # assert dts + dtb + map + coverage generated
```

- [ ] **Step 2: Run test to verify expected behavior**

Run: `pytest test/xsa/test_pipeline.py -v -k real_sdtgen`  
Expected: FAIL before implementation, then PASS/SKIP after.

- [ ] **Step 3: Implement guarded integration flow**

```python
# use shutil.which("sdtgen") and fixture discovery
# skip with clear reason if tools/fixtures absent
```

- [ ] **Step 4: Run test to verify pass/skip**

Run: `pytest test/xsa/test_pipeline.py -v -k real_sdtgen`  
Expected: PASS or SKIP with explicit reason.

- [ ] **Step 5: Commit**

```bash
git add test/xsa/test_pipeline.py
git commit -m "test(xsa): add real sdtgen integration test for example xsa"
```

### Task 15: Update user docs for full-reference workflow

**Files:**
- Modify: `doc/source/examples/xsa_ad9081_zcu102.md`
- Modify: `doc/source/xsa.rst`

- [ ] **Step 1: Write failing doc checks (if repo has docs test target)**

Run: `pytest -q doc || true`  
Expected: either missing target or failures to be resolved.

- [ ] **Step 2: Update docs with new command and artifacts**

```rst
adidtc xsa2dt -x examples/xsa/system_top.xsa -c cfg.json \
  --reference-dts-root path/to/zynqmp-zcu102-rev10-ad9081-m8-l4.dts

Outputs:
- *.dts
- *.dtb
- *.map.json
- *.coverage.md
```

- [ ] **Step 3: Build docs to verify no syntax errors**

Run: `make -C doc html`  
Expected: build success.

- [ ] **Step 4: Commit**

```bash
git add doc/source/examples/xsa_ad9081_zcu102.md doc/source/xsa.rst
git commit -m "docs(xsa): document full reference-driven mapping workflow and artifacts"
```

### Task 16: Verify Chunk 4 and final full-suite evidence

**Files:**
- Test: `test/xsa`
- Test: `test/hw`
- Test: `test/hw_xsa`

- [ ] **Step 1: Run complete non-hardware regression suite**

Run: `pytest test/xsa -v`  
Expected: PASS.

- [ ] **Step 2: Run targeted hardware paths**

Run: `pytest test/hw/test_ad9081_new.py test/hw/test_ad9081_multirate_hw.py test/hw_xsa -v`  
Expected: PASS/SKIP depending on hardware availability; no unhandled failures.

- [ ] **Step 3: Run final packaging gate**

Run: `pytest -v`  
Expected: PASS, or known hardware skips only.

- [ ] **Step 4: Commit final stabilization changes**

```bash
git add -A
git commit -m "feat(xsa): complete full devicetree mapping pipeline with parity and hardware validation"
```

## Review Checklist per Chunk (apply after writing/adjusting each chunk)

- [ ] No TODO/TBD/placeholders.
- [ ] Chunk aligns with approved spec at `docs/superpowers/specs/2026-03-11-xsa-full-devicetree-mapping-design.md`.
- [ ] Tasks are atomic and independently executable.
- [ ] Steps include explicit verification commands and expected outcomes.
- [ ] File responsibilities remain single-purpose and bounded.

## Execution Notes

- Use @superpowers:test-driven-development before each implementation task.
- Use @superpowers:systematic-debugging for any failing test or unexpected behavior.
- Use @superpowers:verification-before-completion before claiming chunk completion.
- Keep commits small and task-scoped.

