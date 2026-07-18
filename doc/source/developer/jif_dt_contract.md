# pyadi-jif to pyadi-dt interface contract

## Status

This page defines the proposed, versioned agreement between pyadi-jif and
pyadi-dt. The executable pyadi-dt reference model is
{mod}`adidt.jif_contract` and its focused tests are in
`test/test_jif_contract.py`.

The first contract version is intentionally introduced alongside the existing
raw configuration paths. Pipeline and CLI integration can migrate in later,
reviewable changes without changing the contract's ownership boundary.

## Why a contract is needed

pyadi-jif currently returns a solver-oriented dictionary. Keys can be assembled
from component names, such as `jesd_AD9081_RX`, while clock outputs combine
semantic names with positions in `out_dividers`. Existing pyadi-dt flows consume
variants of that result by copying selected JESD keys, indexing divider lists,
or looking up implementation-specific names.

Those dictionaries are useful inside pyadi-jif, but they are not a safe public
interface. In particular, a requested-clock position in pyadi-jif does **not**
identify a physical HMC7044 or AD952x output. Physical placement is board wiring
and therefore belongs to pyadi-dt.

## Contract decision

Use a strict, versioned JSON interchange document with typed projections in
both projects.

- Contract name: `adi.jif-dt`
- Initial version: `1.0`
- Units: integer hertz, named with an `_hz` suffix
- IDs: stable lowercase semantic IDs, independent of Python class names and DT
  labels
- Compatibility: consumers reject unsupported major versions and unknown 1.0
  fields
- Safety: parse, validate, bind, and check topology before rendering or changing
  a device tree

The JSON shape is the public API. Neither project's internal class hierarchy is
part of the agreement. A saved contract can therefore be consumed without
installing a solver backend.

## Ownership boundary

### pyadi-jif owns solved electrical intent

pyadi-jif produces:

- JESD standard, direction, framing, sample rate, and lane rate;
- semantic source/sink clock requirements and solved rates/dividers;
- FPGA transceiver or PLL results needed to implement a link;
- producer and solver provenance.

### pyadi-dt owns physical topology

pyadi-dt supplies:

- XSA-discovered instances and direction;
- DT labels, compatible strings, phandles, and JESD link IDs;
- physical clock-output channel indices;
- SPI buses and chip selects, GPIOs, interrupts, and DMA labels;
- board/profile defaults and final DTS rendering.

### Values that must not cross the boundary

The contract excludes solver expressions and backend objects, arbitrary DT
properties, SPI/GPIO placement, implicit units, and positional
`out_dividers` treated as physical channels.

## Interchange example

```json
{
  "schema": "adi.jif-dt",
  "version": "1.0",
  "producer": {
    "name": "pyadi-jif",
    "version": "0.1.6"
  },
  "jesd_links": [
    {
      "id": "ad9680.rx",
      "direction": "adc-to-fpga",
      "converter": "AD9680",
      "fpga": "zc706",
      "standard": "jesd204b",
      "sample_rate_hz": 1000000000,
      "lane_rate_hz": 10000000000,
      "parameters": {
        "F": 1,
        "K": 32,
        "L": 4,
        "M": 2,
        "N": 16,
        "Np": 16,
        "S": 1,
        "HD": 0,
        "CS": 0,
        "CF": 0
      },
      "fpga_config": {
        "type": "qpll",
        "sys_clk_select": "XCVR_QPLL0"
      }
    }
  ],
  "clock_requirements": [
    {
      "id": "ad9680.device-clock",
      "role": "converter-device",
      "sink": "AD9680",
      "source": "HMC7044",
      "rate_hz": 1000000000,
      "divider": 3
    },
    {
      "id": "ad9680.sysref",
      "role": "converter-sysref",
      "sink": "AD9680",
      "source": "HMC7044",
      "rate_hz": 7812500,
      "divider": 384
    }
  ],
  "metadata": {
    "solver": "CPLEX"
  }
}
```

`fpga_config` and `metadata` are isolated extension points. A consumer must not
require arbitrary keys from either mapping without promoting those keys into a
later contract version.

## Binding semantic intent to a board

{class}`~adidt.jif_contract.JifDtContract` validates the portable result.
{class}`~adidt.jif_contract.JifDtBindings` is a separate pyadi-dt-owned object
that maps semantic IDs to physical endpoints:

```python
from adidt.jif_contract import (
    ClockBinding,
    JesdBinding,
    JifDtBindings,
    JifDtContract,
)

contract = JifDtContract.from_json_file("solved.jif-dt.json")

bindings = JifDtBindings(
    clocks=(
        ClockBinding(
            requirement_id="ad9680.device-clock",
            dt_label="hmc7044",
            output_index=13,
        ),
        ClockBinding(
            requirement_id="ad9680.sysref",
            dt_label="hmc7044",
            output_index=5,
        ),
    ),
    jesd_links=(
        JesdBinding(
            link_id="ad9680.rx",
            converter_label="ad9680",
            jesd_label="axi_ad9680_jesd204_rx",
            xcvr_label="axi_ad9680_adxcvr",
        ),
    ),
)

bindings.check(contract)
```

The check is required before render or apply. Keeping bindings separate permits
one electrical solution to be used with multiple carrier/profile placements
without teaching pyadi-jif about DT labels.

## Runnable examples

The examples under `examples/jif_contract/` are executed by the test suite, so
the documented API and checked-in JSON cannot drift silently.

### Consume a saved AD9680 handoff

This example loads solver output and board bindings from separate JSON files.
It validates both documents and their one-to-one semantic join without
importing pyadi-jif or a solver backend:

```bash
python examples/jif_contract/consume_ad9680.py
```

```{literalinclude} ../../../examples/jif_contract/consume_ad9680.py
:language: python
:caption: examples/jif_contract/consume_ad9680.py
```

The portable electrical result in
`examples/jif_contract/ad9680.jif-dt.json` is generated by pyadi-jif's
`examples/ad9680_jif_dt_contract.py`; the independent illustrative ZC706
placement is `examples/jif_contract/ad9680.bindings.json`. A different carrier
can reuse the contract with a different bindings document.

### Build a bidirectional ADRV9009 handoff

The second example constructs RX and TX links with the typed API, binds their
AD9528 and FPGA endpoints, and checks the whole handoff before any pipeline or
device-tree operation:

```bash
python examples/jif_contract/adrv9009_bidirectional.py
```

```{literalinclude} ../../../examples/jif_contract/adrv9009_bidirectional.py
:language: python
:caption: examples/jif_contract/adrv9009_bidirectional.py
```

## Required validation

### Contract checks

The typed reference model performs side-effect-free checks for:

- exact schema and supported version;
- unknown fields and duplicate semantic IDs;
- positive integer rates and dividers;
- JESD transport identity, `M * S * Np == 8 * L * F`;
- lane-rate consistency using 8b/10b for JESD204B or 64b/66b for JESD204C;
- deterministic JSON serialization and validation on load.

### Binding and topology checks

Before generating DTS, pyadi-dt must additionally ensure:

- every semantic clock and JESD link is bound exactly once;
- bindings contain no unknown IDs;
- independent clocks do not occupy the same physical output;
- clock channel indices are in range for the selected device;
- source device and compatible string agree with the board profile;
- converter, JESD, and transceiver labels exist exactly once in the XSA;
- direction and clock role agree with the target endpoint;
- divider/rate and FPGA PLL selections are supported.

### Apply checks

Generation should first target a temporary or in-memory tree. DTS lint and
`dtc` compilation must pass before an explicit file, SD-card, or live apply.
Failure must not silently substitute a hard-coded configuration.

## Proposed producer API

pyadi-jif should add an explicit export API without initially changing the
historical return value of `system.solve()`:

```python
solution = system.solve()
handoff = system.export_config(
    format="adi.jif-dt",
    solution=solution,
)
handoff.to_json_file("solved.jif-dt.json")
```

The exporter should build links from converter objects rather than parsing
computed dictionary keys. It should zip semantic clock names, rates, and solved
dividers without exporting list position as a physical channel. The returned
handoff should be a detached snapshot with no solver objects reachable through
JSON.

## Proposed consumer API

A later pyadi-dt integration can accept the typed contract alongside existing
raw configuration support:

```python
XsaPipeline().run(
    xsa_path="design.xsa",
    cfg=contract,
    bindings=bindings,
    output_dir="out",
)
```

The consumer sequence is parse, validate, resolve profile, bind semantic IDs,
check XSA topology, check capabilities, convert to internal pipeline config,
then render and lint.

The `adidtc jif clock` command should likewise migrate from positional divider
application to contract plus profile bindings. Legacy JSON can remain behind an
explicit compatibility option for one deprecation cycle, but it must not guess
physical channel placement.

## Errors

Use narrow errors at each boundary:

- `ContractError` for malformed or incompatible interchange;
- `BindingError` for incomplete, duplicate, or impossible profile placement;
- `TopologyMismatchError` when an expected XSA/DT endpoint is absent or has the
  wrong direction;
- `CapabilityError` for unsupported rates, dividers, or link modes;
- existing rendering, compilation, and application exceptions afterward.

Do not catch `Exception` around solve, export, or binding. A caller may choose a
named fallback configuration, but it must be reported as a fallback rather than
as the pyadi-jif solution.

## Test agreement

### pyadi-jif producer tests

1. Golden exports for AD9680, nested ADRV9009, and one MxFE JESD204C system.
2. Exported values match converter objects and historical solve output.
3. Requested-clock reordering does not alter semantic identity.
4. Exported snapshots have detached ownership and deterministic JSON.
5. Gekko and CPLEX produce contract-equivalent fields for the same constraints.
6. No solver/backend object is JSON reachable.

### pyadi-dt consumer tests

The reference suite covers valid parse/bind, unsupported versions, unknown
fields, JESD and lane-rate inconsistencies, duplicate IDs, incomplete bindings,
physical clock collisions, deterministic round trips, and malformed JSON.

Integration tests should add contract-to-pipeline mapping, profile resolution,
XSA mismatch without output mutation, DTS golden output plus compilation/lint,
and CLI dry-run before any write.

### Cross-repository CI

pyadi-jif should own a small canonical fixture corpus and publish the generated
JSON Schema as a release artifact. On pyadi-jif changes, generate fixtures and
run the pyadi-dt consumer. On pyadi-dt changes, consume both canonical fixtures
and artifacts generated by the minimum supported pyadi-jif release and current
main. Hardware-backed configurations can run nightly.

## Compatibility policy

Optional additions may be made within contract 1.x without changing existing
meaning. Required fields, unit changes, enum semantic changes, and ID-rule
changes require contract 2.0. Producer and consumer package versions are
provenance; compatibility is determined by the contract version.

## Rollout

1. Agree on names, ownership, and AD9680/ADRV9009/AD9081 canonical systems.
2. Generate the canonical JSON Schema from the pyadi-jif producer model.
3. Add `system.export_config(format="adi.jif-dt")` and producer tests.
4. Add pyadi-dt profile bindings and contract-to-pipeline translation.
5. Convert `adidtc jif clock` and require dry-run validation.
6. Convert board helpers and remove broad solver fallback.
7. Enable cross-repository CI, then deprecate positional/raw JSON.

Acceptance requires that saved output works without solver imports, requested
clock ordering cannot change physical placement, all endpoints bind exactly
once, and invalid input fails before any tree mutation.
