# XSA-to-Full-Devicetree Mapping Design (Reference-Driven)

**Date:** 2026-03-11  
**Owner:** pyadi-dt-xsa-powers  
**Status:** Approved for planning  
**Topic:** Generate full, structurally equivalent ADI devicetrees from Vivado XSA + SDTGen + pyadi-jif, starting with AD9081 + ZCU102 and scaling to additional boards.

## Goal

Build a programmatic pipeline that generates a complete DTS/DTB from XSA inputs with structural parity against ADI Linux reference devicetrees (not line-by-line parity), and validates outputs with both existing and dedicated hardware tests.

Initial golden target:
- XSA baseline: `examples/xsa/system_top.xsa`
- Reference DTS family root: `zynqmp-zcu102-rev10-ad9081-m8-l4.dts` and included `.dtsi` dependencies

## Success Criteria

A build is considered successful when all conditions below are met:

1. SDTGen + XSA pipeline emits a merged DTS and compiled DTB.
2. All non-optional roles from the reference manifest are mapped.
3. All required role-to-role links (phandles/graph edges) are emitted.
4. All required per-role properties are present in generated tree.
5. Output passes hardware validation in:
- Existing pytest hardware tests (extended to use generated DTB)
- Dedicated XSA/SDTGen hardware tests

## Non-Goals

- Line-order or textual parity with reference source files.
- Supporting every ADI platform in first delivery.
- Replacing existing `gen-dts` flow.

## Architecture

### 1) Ingestion Layer

Inputs:
- Vivado `.xsa`
- SDTGen generated base DTS
- pyadi-jif configuration JSON
- ADI Linux reference DTS root + included `.dtsi` files

Outputs:
- `HardwareGraph` (normalized view of discovered HW and connectivity)
- `DriverManifest` (reference-driven role requirements)

### 2) Reference Manifest Layer

Parse the reference DTS include graph and extract role requirements:
- Role identity (`ad9081_core`, `jesd_rx_link`, `jesd_tx_link`, `clock_chip`, etc.)
- Matching hints (`compatible`, label/pattern hints, expected parent bus class)
- Required properties
- Required links to other roles
- Multiplicity (`required single`, `required many`, `optional`)

### 3) Mapping Layer

Resolve `DriverManifest` roles against `HardwareGraph` and config values.

For each role resolution, record provenance per field:
- `from_xsa`
- `from_sdtgen`
- `from_jif`
- `defaulted`

Emit `MappingResult` with:
- Resolved role->node specs
- Gap list with reason codes
- Warnings for assumptions/defaults

### 4) Emission/Merge Layer

Use SDTGen DTS as base and inject mapped nodes/links.

Outputs:
- `<name>.dts`
- `<name>.dtb`
- `<name>.map.json`
- `<name>.coverage.md`

### 5) Validation Layer

- Structural parity checker against manifest requirements.
- DTS compile gate via `dtc`.
- Hardware execution gates (existing + dedicated suites).

## Data Contracts

### HardwareGraph

Node fields:
- `instance`
- `ip_type`
- `compatible?`
- `reg`
- `irq`
- `clocks`
- `bus_parent`
- `ports`

Edge classes:
- `clock`
- `reset`
- `jesd_link`
- `spi_control`
- `dma_stream`

### DriverManifest

Each role includes:
- `match_hints`
- `required_properties`
- `required_links`
- `multiplicity`
- `optional` flag

### MappingResult

- `mapped_roles`
- `gaps` with reason enum:
  - `missing_in_xsa`
  - `missing_in_sdtgen`
  - `missing_in_jif`
  - `unsupported_role`
- `warnings`

## Repository Layout (Planned)

- `adidt/xsa/` (existing orchestration/parsing)
- `adidt/xsa/reference/` (new: manifest extractor + schema)
- `adidt/xsa/mapping/` (new: resolver engine + parity checker)
- `adidt/build/pyadi_build_vendor/` (new: vendored pyadi-build components)
- `test/xsa/` (expanded unit/integration tests)
- `test/hw/` (existing suite extended)
- `test/hw_xsa/` (new dedicated XSA hardware suite)

## pyadi-build Integration Strategy

Selected reusable pieces from `tfcollins/pyadi-build` will be vendored locally for deterministic control:
- build invocation helpers
- artifact staging
- reusable board deploy/run helpers where generic

A thin adapter in `adidt/build/` isolates vendored internals from pipeline consumers.

## Testing Strategy

### Unit

- Manifest extraction from reference DTS include tree
- Role schema validation
- Mapper resolution behavior and gap classification
- Parity checker semantics

### Integration (toolchain available)

- Full run on `examples/xsa/system_top.xsa`
- SDTGen base DTS generation
- Merged DTS + DTB generation
- Structural parity report generation

### Hardware

1. Existing hardware tests gain generated-DTB input path.
2. Dedicated `hw_xsa` suite validates:
- boot/deploy path
- expected driver bindings
- JESD link-up smoke criteria

## Error Handling Model

Hard failures:
- Missing required manifest roles
- Missing required links
- Missing required role properties
- `dtc` compile failure

Soft warnings:
- Optional roles unresolved
- Non-critical defaulted values
- Alternate SDTGen naming normalized by mapper

## Phased Rollout

1. Implement AD9081 + ZCU102 structural parity path end-to-end.
2. Land test coverage and hardware execution path in both suites.
3. Generalize manifest/mapper with additional board manifests and role packs.

## Risks and Mitigations

- SDTGen naming/version drift:
  - Mitigation: normalization rules + provenance + explicit gap reasons.

- Overfitting to one reference tree:
  - Mitigation: role schema separates identity from board-specific hints.

- Hardware test flakiness:
  - Mitigation: reuse existing stable helpers and maintain dedicated smoke scope.

## Open Decisions (for planning, not blockers)

- Exact first set of non-AD9081 role packs to support after golden path.
- Policy for tolerant vs strict property equivalence on optional debug nodes.

## Approved Design Summary

Use a reference-driven mapping architecture as the system of record for parity. Treat SDTGen output as base infrastructure, then satisfy manifest-defined driver-role requirements via programmatic mapping from XSA + SDTGen + pyadi-jif data. Validate with compile gates plus both existing and dedicated hardware test flows.
