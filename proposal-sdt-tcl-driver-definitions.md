# Feature proposal: MDD-style Tcl driver definitions for SDT/PetaLinux generation

## Summary

Add an **SDT driver authoring and test framework** to pyadi-dt. The framework lets an ADI FPGA IP driver keep an MDD-like declarative definition inside its Tcl implementation while retaining the procedural `<driver>_generate` entry point required by AMD's `system-device-tree-xlnx` flow.

The proof of concept should implement one real driver, `axi_jesd204_rx`, and demonstrate this path:

```text
ADI IP/XSA
   │
   ├── driver definition + generator Tcl
   │       ├── metadata lint (stock tclsh, no Vivado)
   │       └── mocked generator contract test (stock tclsh)
   │
   ├── staged CUSTOM_SDT_REPO
   │       └── sdtgen + real HSI/XSA
   │               ├── system-top.dts / pl.dtsi
   │               ├── dtc + dt-schema checks
   │               └── semantic parity checks in pyadi-dt
   │
   └── PetaLinux device-tree recipe
           ├── petalinux-build -c device-tree
           └── optional labgrid boot/probe test
```

This makes Tcl support for ADI IP reviewable and testable before it is submitted to `system-device-tree-xlnx`, and gives pyadi-dt a reproducible way to validate the exact driver implementation used by SDTGen/PetaLinux rather than compensating only after generation.

## Motivation

pyadi-dt currently has good tests around:

- XSA parsing and topology discovery;
- `sdtgen` subprocess behavior;
- generated DTS linting and `dtc` compilation;
- PetaLinux `system-user.dtsi` formatting and installation;
- full PetaLinux device-tree build and hardware boot tests.

The missing layer is the **SDT Tcl driver itself**. AMD's legacy `embeddedsw` drivers pair an MDD file with procedural Tcl. Current `system-device-tree-xlnx` instead has one procedural `data/<driver>.tcl` file per driver and a hard-coded IP-to-driver registry. There is no machine-readable contract describing:

- which IP names or VLNVs the driver supports;
- its generator entry point;
- required HSI properties and interfaces;
- the DTS file, nodes, compatibles, and properties it is expected to emit;
- applicable architecture/tool versions;
- the Linux binding against which output should be validated.

As a result, a missing registry entry, misspelled HSI parameter, wrong property type, or stale compatible string is normally found only during a licensed-tool run or boot test.

A local baseline run using the pyadi-dt `test/hw/xsa/system_top.xsa`, SDTGen 2025.1, and an upstream `system-device-tree-xlnx` checkout confirmed that:

1. `CUSTOM_SDT_REPO` is accepted and its Tcl sources are loaded;
2. HSI opens the checked-in XSA successfully;
3. SDTGen generates `system-top.dts`, `pl.dtsi`, and related files;
4. the result compiles with `dtc` (with existing upstream warnings);
5. the fixture contains suitable ADI IPs, including `axi_jesd204_rx`, `axi_jesd204_tx`, `axi_adxcvr`, and `axi_dmac`.

This gives the POC a real, checked-in integration fixture.

## Goals

1. Define a small, versioned, MDD-style contract embedded in Tcl.
2. Make definitions inspectable with stock `tclsh`, without HSI/Vivado/Vitis.
3. Test the generator's observable DTS operations with mocked Tcl APIs.
4. Stage drivers into a complete, pinned `system-device-tree-xlnx` checkout and run real SDTGen against checked-in XSA fixtures.
5. Reuse pyadi-dt's DTS parser, linter, `dtc`, parity, PetaLinux, and hardware-test infrastructure.
6. Produce artifacts suitable for upstreaming to `system-device-tree-xlnx`.
7. Keep the POC narrow enough to validate the architecture before converting other ADI IPs.

## Non-goals for the POC

- Reimplementing HSI or SDTGen in Python.
- Replacing Linux DT binding documentation (YAML or legacy text) with a second schema language.
- Converting every ADI IP in the first change.
- Reintroducing the legacy PSF/MDD file format as a separate file.
- Replacing pyadi-dt's board-level converter/clock/JESD configuration overlays.
- Requiring Vivado, Vitis, or PetaLinux for normal pull-request unit tests.

## Proposed Tcl contract

Each driver remains a normal `system-device-tree-xlnx` Tcl implementation and retains the expected global generator adapter. It additionally exposes a side-effect-free definition proc in a driver-specific namespace.

```tcl
namespace eval ::adidt::sdt::axi_jesd204_rx {
    variable definition [dict create \
        schema_version 1 \
        name axi_jesd204_rx \
        supported_ip_names {axi_jesd204_rx} \
        supported_vlnv_globs {analog.com:user:axi_jesd204_rx:*} \
        generator_proc axi_jesd204_rx_generate \
        output_files {pl.dtsi} \
        architectures {zynq zynqmp versal microblaze} \
        required_hsi_properties {
            CONFIG.C_NUM_LANES
            CONFIG.C_DATA_PATH_WIDTH
            CONFIG.C_LINK_MODE
            CONFIG.C_NUM_LINKS
        } \
        required_interfaces {s_axi core_clk s_axi_aclk irq} \
        compatibles {adi,axi-jesd204-rx-1.0} \
        binding Documentation/devicetree/bindings/iio/jesd204/adi,jesd204-rx.txt \
        binding_format legacy-text \
        emitted_properties [dict create \
            compatible stringlist \
            reg reg \
            interrupts intlist \
            clocks phandle-array \
            clock-names stringlist \
            adi,octets-per-frame int \
            adi,frames-per-multiframe int \
            adi,high-density boolean]]

    proc definition {} {
        variable definition
        return $definition
    }
}

# Compatibility entry point expected by system-device-tree-xlnx.
proc axi_jesd204_rx_generate {drv_handle} {
    ::adidt::sdt::axi_jesd204_rx::generate $drv_handle
}
```

The current ADI Linux tree documents this IP in the legacy text binding shown above; it permits compatibles `adi,axi-jesd204-rx-1.0` and `adi,axi-jesd204-rx-1.3`, requires `reg`, `interrupts`, `clocks`, `clock-names`, `adi,frames-per-multiframe`, and `adi,octets-per-frame`, and makes `adi,high-density` optional. The implementation must also audit the current driver and existing pyadi-dt `BoardModel`/builder output because the binding may lag newer JESD204C/framework behavior. Migrating that binding to YAML is useful follow-up work, but is not required to prove the Tcl contract.

### Contract rules

- `definition` must not call HSI, access the filesystem, or mutate a device tree.
- `schema_version`, `name`, `supported_ip_names`, `generator_proc`, and `output_files` are required.
- Every named generator proc must exist after sourcing the file.
- Property types use a small vocabulary mapped to both SDT Tcl helpers and DTS/schema expectations.
- `supported_ip_names` drives registry generation/checking; it must not be duplicated manually in pyadi-dt.
- Linux binding paths are references, not copied schemas; both YAML and legacy text bindings are supported and identified by `binding_format`.
- Architecture/tool constraints are explicit and testable.
- Driver-specific procedural logic remains allowed; the definition is a contract, not a restrictive code generator.

## Repository layout

Proposed pyadi-dt additions:

```text
adidt/sdt/
├── definitions.py              # typed definition model and validation
├── tcl.py                      # safe tclsh invocation and result decoding
├── staging.py                  # build a complete CUSTOM_SDT_REPO worktree
├── registry.py                 # registry validation/patch generation
└── drivers/
    └── axi_jesd204_rx/
        └── data/
            └── axi_jesd204_rx.tcl

test/sdt/
├── fixtures/
│   ├── mock_hsi.tcl
│   ├── mock_dt.tcl
│   └── axi_jesd204_rx_expected.json
├── test_definition_contract.py
├── test_tcl_generator.py
├── test_registry.py
├── test_sdtgen_integration.py
└── test_petalinux_integration.py
```

The Tcl files must be included in wheel and sdist package data. The staged repository is generated in a temporary/cache directory and is not vendored into the wheel.

## User-facing tooling

Add an `adidtc sdt-driver` command group:

```bash
# Scaffold a namespaced Tcl definition and tests
adidtc sdt-driver init axi_jesd204_rx \
  --ip-name axi_jesd204_rx \
  --vlnv 'analog.com:user:axi_jesd204_rx:*'

# Validate all definitions with stock tclsh
adidtc sdt-driver lint

# Run a generator against mocked HSI/DT APIs
adidtc sdt-driver test axi_jesd204_rx \
  --fixture test/sdt/fixtures/axi_jesd204_rx.json

# Stage a complete custom SDT repository using a pinned upstream revision
adidtc sdt-driver stage \
  --upstream /path/to/system-device-tree-xlnx \
  --output .cache/adidt/sdt-repo

# Real XSA/HSI verification
adidtc sdt-driver verify axi_jesd204_rx \
  --xsa test/hw/xsa/system_top.xsa \
  --sdt-repo .cache/adidt/sdt-repo \
  --output build/sdt-driver/axi_jesd204_rx
```

`verify` should emit a machine-readable report containing:

- pyadi-dt revision;
- SDT Tcl driver content hash;
- `system-device-tree-xlnx` revision;
- SDTGen/Vivado/Vitis version;
- selected XSA hash and matched IP instances;
- definition validation results;
- emitted node/property inventory;
- `dtc`, dt-schema, lint, and parity results;
- paths to generated DTS/DTB/log artifacts.

## Staging and registry integration

A driver directory alone is not enough. Current SDTGen generation dispatch is controlled by `::sdtgen::namespacelist` in `device_tree/data/device_tree.tcl`. Driver lookup mappings are duplicated in `device_tree/data/common_proc.tcl` and the legacy/software helper registry in `device_tree/data/xillib_sw.tcl`. The generation loop uses the namespace map to source `<driver>/data/<driver>.tcl` and call `<driver>_generate`, while common property and alias helpers call `get_drivers`. Staging must patch and verify all three registries.

The staging tool therefore must:

1. require a complete checkout of a supported `system-device-tree-xlnx` revision;
2. create an isolated worktree/copy rather than mutate the user's checkout;
3. copy the selected ADI driver directories into that tree;
4. derive IP-name mappings from `supported_ip_names`;
5. insert or validate registry entries idempotently;
6. reject collisions where an IP is already mapped to a different driver;
7. write a manifest of all copied and patched files;
8. expose the staged path through `CUSTOM_SDT_REPO` only for the child process.

The long-term upstream result should be ordinary driver Tcl plus registry changes in `system-device-tree-xlnx`; the pyadi-dt staging layer is an authoring/test bridge, not a permanent fork.

## Proof of concept scope

### Driver

Use `axi_jesd204_rx` with ADRV9009+ZC706. The lab XSA contains both the primary and observation receive instances, so the POC verifies repeated dispatch of the same driver:

```text
instances: axi_adrv9009_rx_jesd_rx_axi,
           axi_adrv9009_rx_os_jesd_rx_axi
IP name:   axi_jesd204_rx
VLNV:      analog.com:user:axi_jesd204_rx:1.0
```

The current generic SDT output creates the node but emits a Xilinx-compatible form such as:

```dts
axi_adrv9009_rx_jesd_rx_axi: axi_jesd204_rx@44aa0000 {
    compatible = "xlnx,axi-jesd204-rx-1.0";
    xlnx,num-lanes = <4>;
    xlnx,data-path-width = <4>;
    ...
};
```

The POC driver must demonstrate a deliberate, binding-backed ADI result and prove which properties are generated from HSI versus supplied later by pyadi-dt's board/JESD configuration layer. It must not silently duplicate or conflict with the existing overlay.

### Required POC behavior

1. The definition is discoverable without HSI.
2. The fixture's IP name and VLNV match the definition.
3. The generator runs under a mock API and emits the expected compatible and typed properties.
4. Staging creates a valid custom SDT repository and registry mapping.
5. SDTGen 2025.1 runs against `test/hw/xsa/system_top.xsa` with that repository.
6. The generated node is found by instance label/address and satisfies the definition.
7. The generated tree compiles with `dtc`.
8. Existing pyadi-dt overlay generation merges without duplicate labels/properties or incompatible values.
9. The final merged/PetaLinux tree passes pyadi-dt lint and semantic parity checks.
10. The integration report is retained as a CI artifact.

A follow-up should add `axi_jesd204_tx`, which is structurally similar and will reveal whether the definition model generalizes without prematurely broadening the first implementation.

## Test strategy

### Tier 1: definition tests — every PR, no vendor tools

Run with Python plus stock `tclsh`:

- source each driver Tcl in a restricted harness;
- call its namespaced `definition` proc;
- serialize the Tcl dict to JSON through a small Tcl harness;
- validate against a Pydantic model;
- verify required keys, schema version, generator existence, unique names/IP mappings, allowed property types, and package inclusion;
- reject top-level side effects by stubbing unknown commands to fail during definition loading;
- verify deterministic output from repeated definition calls.

Do not parse Tcl with regular expressions. Let Tcl parse Tcl.

### Tier 2: mocked generator tests — every PR, no vendor tools

Provide minimal Tcl implementations of the APIs used by the POC driver:

- `hsi::get_cells`, `hsi get_property`, and connection/property queries;
- `get_node`, `set_drv_def_dts`, `add_prop`, `set_drv_conf_prop`, and `create_node`;
- an operation recorder that emits JSON.

Assertions should compare semantic operations, not whitespace:

```json
{
  "node": "axi_mxfe_rx_jesd_rx_axi",
  "property": "compatible",
  "type": "stringlist",
  "value": ["adi,axi-jesd204-rx-1.0"]
}
```

Negative fixtures must cover a missing required HSI parameter, unsupported IP version, wrong property type, and missing clock/interrupt connection.

### Tier 3: static cross-checks — every PR

- Cross-check `supported_ip_names` against the staged/generated SDT registry.
- Cross-check emitted properties and compatible strings against the referenced Linux binding. Reuse pyadi-dt's binding audit tooling for YAML and add a small legacy-text adapter for this POC binding.
- Scan checked-in XSA/HWH fixtures and report definition coverage.
- Ensure every definition has at least one fixture or an explicit untested rationale.
- Run `ruff`, type checking, package build, and installed-wheel discovery tests.

### Tier 4: real SDTGen integration — licensed self-hosted runner

For each supported toolchain leg (start with 2025.1):

```bash
export CUSTOM_SDT_REPO="$STAGED_SDT_REPO"
sdtgen -eval \
  "set_dt_param -xsa {$XSA} -dir {$OUT}; generate_sdt"
cpp -nostdinc -undef -x assembler-with-cpp -I "$OUT" \
  "$OUT/system-top.dts" > "$OUT/system-top.pp.dts"
dtc -I dts -O dtb -o "$OUT/system-top.dtb" "$OUT/system-top.pp.dts"
```

Then run pyadi-dt's structural linter and semantic assertions against the generated node. Pin the upstream SDT repository revision and record it in the report.

A complete SDT checkout is mandatory. A sparse checkout containing only the POC driver is insufficient because generation also sources processor and platform drivers.

### Tier 5: PetaLinux build integration — labeled/nightly

Extend the existing PetaLinux harness to select a staged driver repository and build only the device-tree recipe:

```bash
petalinux-config --get-hw-description=<isolated-xsa-dir> --silentconfig
petalinux-build -c device-tree
```

The test must inspect `images/linux/system.dtb`, not only `system-user.dtsi`, and assert:

- the target node has the expected ADI compatible;
- required clocks, interrupts, and register ranges survived DTG/BitBake processing;
- no duplicate node/label was introduced by the pyadi-dt overlay;
- the final DTB passes the same semantic contract as the SDTGen artifact.

Because propagation of `CUSTOM_SDT_REPO` through a given PetaLinux release must be proven rather than assumed, the POC should first add an environment/preflight check that records which SDT repository the PetaLinux DTG actually sourced. If the release does not honor it, stage the Tcl into an isolated tool/project repository through an explicit adapter rather than modifying the global installation.

### Tier 6: hardware validation — manual label/nightly

Reuse the existing labgrid path:

- boot the PetaLinux-generated DTB;
- assert no kernel faults;
- assert the expected IIO devices probe;
- assert JESD204 reaches DATA state;
- run a minimal RX capture.

This tier validates behavior but should not be the first place a definition error is discovered.

## CI integration

Recommended jobs:

| Job | Environment | Trigger | Required |
|---|---|---|---|
| `sdt-driver-contract` | GitHub-hosted Ubuntu + `tclsh` | every PR | yes |
| `sdt-driver-mock` | GitHub-hosted Ubuntu + `tclsh` | every PR | yes |
| `sdt-driver-binding` | GitHub-hosted Ubuntu + binding cache | every PR | yes |
| `sdt-driver-sdtgen-2025.1` | licensed self-hosted runner | label, main, nightly | required for Tcl-driver changes |
| `sdt-driver-petalinux` | PetaLinux self-hosted runner | label, main, nightly | required before release/upstream submission |
| `sdt-driver-hardware` | labgrid runner | `hw-test` label/nightly | required before declaring hardware support |

Use a changed-files filter so licensed jobs run automatically when these paths change:

```text
adidt/sdt/**
test/sdt/**
adidt/xsa/parse/sdtgen.py
adidt/xsa/merge/**
.github/workflows/*sdt*
```

Upload staged-repository manifests, Tcl operation logs, generated DTS/DTB, validation JSON, and tool versions even on failure.

## Implementation phases

### Phase 1 — contract spike

- Add the typed Python definition model.
- Add the stock-`tclsh` loader/harness.
- Add one inert `axi_jesd204_rx` definition and contract tests.
- Confirm definition discovery works from an installed wheel.

**Exit criterion:** no vendor tools are needed to validate the metadata contract.

### Phase 2 — mocked generation

- Implement the minimal generator Tcl.
- Add mock HSI/DT APIs and semantic operation snapshots.
- Add positive and negative fixtures.
- Cross-check compatible/properties with the Linux binding.

**Exit criterion:** generator behavior is deterministic and reviewable on GitHub-hosted CI.

### Phase 3 — real SDTGen staging

- Add complete-repository staging and registry patching.
- Pin a supported `system-device-tree-xlnx` revision.
- Run the checked-in AD9081 XSA through SDTGen 2025.1.
- Compile and inspect generated output; compare with the current baseline and pyadi-dt overlay.

**Exit criterion:** the POC changes the intended node only, with a machine-readable diff and green `dtc`/lint/parity checks.

### Phase 4 — PetaLinux and hardware

- Prove how the selected PetaLinux release consumes the staged Tcl repository.
- Build `system.dtb` using `petalinux-build -c device-tree`.
- Add an opt-in labgrid boot/probe test.

**Exit criterion:** the final PetaLinux DTB boots and the ADI/JESD device probes successfully.

### Phase 5 — upstream path

- Generate a clean patch for `system-device-tree-xlnx` containing the Tcl driver and registry entry.
- Keep the pyadi-dt contract/tests as the conformance suite.
- Add `axi_jesd204_tx` only after the RX POC has proven the model.

## Acceptance criteria

The POC is complete when:

- [ ] `axi_jesd204_rx.tcl` exposes a schema-versioned, side-effect-free definition.
- [ ] `adidtc sdt-driver lint/test/stage/verify` provide actionable failures.
- [ ] stock-`tclsh` contract and mocked-generator tests run on normal CI.
- [ ] an installed wheel contains and discovers the Tcl definition.
- [ ] a complete staged `system-device-tree-xlnx` checkout is generated without mutating its source checkout.
- [ ] SDTGen 2025.1 uses the staged repository and the checked-in XSA.
- [ ] generated DTS compiles and passes pyadi-dt lint/binding/parity checks.
- [ ] pyadi-dt overlay behavior is explicitly reconciled with Tcl output; no duplicate or conflicting properties remain.
- [ ] PetaLinux builds a final `system.dtb` whose target node satisfies the same contract.
- [ ] CI retains tool versions, repository revisions, generated trees, semantic diff, and logs.
- [ ] one hardware run confirms probe and JESD DATA state before support is declared.

## Risks and mitigations

### Tcl definitions become a second binding schema

Keep the metadata focused on driver dispatch, dependencies, and expected output. Linux binding YAML remains authoritative for property semantics, and tests cross-check rather than copy the full binding.

### Mock APIs diverge from HSI

Use mocks only for fast behavior tests. Require real SDTGen integration for Tcl changes and keep captured HSI fixtures/version metadata.

### pyadi-dt and Tcl both write the same node

Treat this as a first-class parity test. Define ownership per property: hardware-discoverable values belong in Tcl; board/solver-derived values remain in pyadi-dt. Merge must reject conflicting duplicate values.

### Registry patching is brittle

Use definition-derived mappings, parse/modify a narrowly recognized registry form, verify idempotence, and fail closed on unexpected upstream structure. Emit a patch for review.

### Vendor version drift

Pin and report the supported SDT revision/tool version, test at least one current release, and add a matrix only after the POC. Contract tests remain version-independent.

### PetaLinux ignores `CUSTOM_SDT_REPO`

Add a preflight provenance assertion. Never claim PetaLinux coverage based solely on an SDTGen run. Use an isolated project/tool repository adapter if necessary; do not patch a global installation in CI.

## Recommended first pull requests

1. **Contract and loader:** typed model, Tcl definition loader, package data, and unit tests.
2. **RX driver mock POC:** `axi_jesd204_rx` Tcl generator, mock API, binding checks, and fixtures.
3. **SDT staging/integration:** registry generation, pinned upstream staging, real SDTGen job, DTS semantic diff.
4. **PetaLinux integration:** provenance preflight, device-tree recipe build, final-DTB assertions.
5. **Hardware/upstream:** labgrid validation and an upstream-ready `system-device-tree-xlnx` patch.

This sequence keeps each change reviewable and prevents licensed-tool or hardware failures from masking basic definition errors.
