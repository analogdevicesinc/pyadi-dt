# Release hardening candidate — 2026-11-10

This candidate is the `fix/release-hardening` branch based on `92e6fc8`. It is
not tagged or released. GitHub checks and artifacts identify the exact PR head
commit; repeat the release dry run and hardware checks for the final commit
before tagging. No previous hardware result qualifies this branch.

## Software checks

The candidate fixes all ten findings from the main-branch review:

- PyPI-safe metadata: Git-only lab tools moved to source requirements.
- A clean, isolated wheel `[xsa]` installation exercises imports, profile
  discovery and CLI help; `requests` is declared in the extra.
- Nested AXI children retain their structure; compiled DTB path checks verify
  generated IP is under the bus. Both ADRV9040 layouts resolve SDTGen-style
  `gic_a53` references in the merged DTS and overlay.
- Both PetaLinux pipeline entry points execute; ZynqMP output uses `gic_a53`.
- Typed and raw implicit JESD framing agree after topology detection, including
  partial ORX settings and explicit `F=1` overrides.
- MCP reads actual DTS and DTB fixtures by short name, full path and compatible.
- Failed release-asset downloads fail checksum refresh.
- Tag workflows use a shared queue that retains all pending publication runs.
- Type checking and dependency audit preserve nonzero checker exits; the
  existing clock/MxFE type errors are fixed with generic model types.
- CodeQL is an explicit Python/Actions workflow, avoiding C/C++ fixture headers.

Local validation after the DataX hardware-CI migration: **1108 passed, 15 skipped**.
The migration adds 84 tests for kernel handoff, preparation, release selection,
pre-acquisition checks, and job-owned reservation cleanup.
Ruff and ty 0.0.100 passed. The renamed import rule is updated so hosted
checking exits successfully.
Bandit passed against the existing baseline, and the runtime dependency audit
reported no known vulnerabilities. Source/wheel builds, `twine check`, clean
wheel `[xsa]` installation, and strict Sphinx `dirhtml` builds passed.

Reproduce the software checks from the candidate checkout:

```sh
pytest -q
ruff check adidt test
ty check adidt/model/ adidt/xsa/build/builders/ adidt/devices/ adidt/system.py adidt/tools/
bandit -r adidt -c .bandit -b .bandit-baseline.json
pip-audit -r requirements.txt
python -m build
python .github/scripts/verify-release-wheel.py dist/*.whl --smoke-xsa
twine check dist/*
sphinx-build -W --keep-going -b dirhtml doc/source doc/build/dirhtml
```

The final fresh-context review found a generic typed framing regression;
its reproducer failed before the topology-aware default resolution fix and
passed afterward, together with the full suite. The hosted release build also runs the clean-wheel
smoke check; building a wheel or passing `twine check` alone does not establish
PyPI upload acceptance.

## Outstanding release gates

Hardware CI now uses public `tfcollins/datax-manifests` at
`6efed11c826f35f5e3a5da3c10ebd54c309f25fa`, driven by checksum-verified CIM
v1.2.4. The `adi-linux` target prepares artifacts before board acquisition,
with consumer-side source pin and image checksum validation. The earlier
[authentication failure](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/42780867296)
is superseded by this migration. Exact-head hardware results must be reviewed
before release qualification.

The earlier [C/C++ CodeQL run](https://github.com/analogdevicesinc/pyadi-dt/actions/runs/42749801840)
failed with “No source files found.” The committed advanced workflow replaces
language autodetection with Python and Actions. Managed default setup must be
disabled for advanced SARIF uploads to work.

ADRV9040 validation remains software-only with representative HWH fixtures and
a controlled SDTGen base. Real SDTGen/Vivado execution, physical boot, JESD
training and RF operation are unqualified. External firmware, ACE profiles and
gain tables remain user-supplied. No new Kuiper release compatibility is claimed.

No tag, GitHub Release, PyPI publication or hardware qualification is produced
by this hardening work. Trusted publishing and the release-reviewer environment
still require operator verification per the [runbook](release_runbook.md).
