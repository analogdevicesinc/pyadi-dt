# Release Operator Runbook

This runbook covers validation, publication, verification, and recovery for a
`pyadi-dt` release. The **Publish Release** workflow builds on manual dispatch but
publishes only when an annotated `v*` tag is pushed.

The [2026-09-05 readiness audit](release_readiness_2026-09-05.md) records
candidate checks and unresolved hardware coverage; refresh that evidence for
the final release commit.

## One-time setup

### PyPI trusted publisher

Before the first release, sign in to PyPI and add a **pending trusted
publisher** with these exact values:

- PyPI project name: `pyadi-dt`
- Owner: `analogdevicesinc`
- Repository: `pyadi-dt`
- Workflow: `release.yml`
- Environment: `pypi`

After the first successful upload, verify that the pending publisher became a
publisher for the newly created project.

### GitHub environment

Create a GitHub environment named `pypi`. Require a release reviewer and limit
deployment refs to tags matching `v*`. The PyPI job requests OIDC only inside
this environment; no PyPI API token is required.

## Prepare and validate

1. Confirm the target version agrees in `pyproject.toml` and
   `adidt/__init__.py` and has a non-empty `## [X.Y.Z]` section in
   `CHANGELOG.md`.
2. Run the local contract and package checks from a clean checkout:

   ```bash
   git fetch origin --tags
   git switch main
   git pull --ff-only origin main
   test -z "$(git status --porcelain)"
   python .github/scripts/release_preflight.py --tag vX.Y.Z
   pytest
   rm -rf build dist
   python -m build
   twine check dist/*
   ```

   The hosted build stages only `.whl` and `.tar.gz` files into `pypi-dist/`
   using `.github/scripts/stage-pypi-artifacts.sh`, and validates that directory
   on both dry runs and tag builds. `SHA256SUMS` stays with the GitHub release
   assets; it must not enter the PyPI action's upload directory.

3. Run the hosted dry run from the candidate branch (or `main` after merge). The candidate tag does **not** need to
   exist yet:

   ```bash
   gh workflow run release.yml --ref YOUR_CANDIDATE_BRANCH -f tag=vX.Y.Z
   gh run watch --exit-status
   ```

   Confirm the validation, Python 3.10–3.14, build, wheel-install, and CLI
   smoke-test jobs pass. The GitHub Release and PyPI jobs must be skipped.
4. Confirm all required `main` workflows—including hardware, Kuiper/Ubuntu
   Debian packaging, and native system packaging—are green for the exact commit
   to be tagged. The native workflow builds on Debian 12, Fedora 42, and macOS
   14 rather than cross-packaging those artifacts on Ubuntu.

   Hardware jobs must select tests and produce at least one passing testcase;
   skip-only jobs are failures. This minimum gate does not certify every test
   path: review individual skips and record unavailable boards separately.
   Generated-DTB evidence requires a boot strategy that actually deploys the
   staged DTB, rather than booting the existing SD tree.

## Tag and publish

Record and inspect the exact release commit before tagging:

```bash
git switch main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
RELEASE_SHA=$(git rev-parse HEAD)
git show --stat "$RELEASE_SHA"
git tag -a vX.Y.Z "$RELEASE_SHA" -m "Release vX.Y.Z"
test "$(git cat-file -t refs/tags/vX.Y.Z)" = tag
git push origin refs/tags/vX.Y.Z
```

The tag push is the only event that permits the workflow's GitHub Release and
PyPI jobs to run. Approve the `pypi` environment deployment only after checking
that the run's tag, commit SHA, version, changelog, tests, and built artifacts
are correct.

## Verify the published release

1. Confirm **Publish Release** completed successfully for the tagged SHA.
2. Confirm both packaging workflows completed for the same tag. The release
   must contain Kuiper/Ubuntu `.deb` files plus the Debian 12 `.deb`, Fedora 42
   `.rpm`, and macOS 14 `.pkg` artifacts. Each job installs and smoke-tests its
   package before upload.
3. Verify the GitHub Release contains the wheel, source distribution, release
   notes, all native system packages, and the `SHA256SUMS` manifest file.
4. Verify checksum manifest integrity:

   ```bash
   gh release download vX.Y.Z -D /tmp/adidt-verify-assets
   cd /tmp/adidt-verify-assets
   sha256sum -c SHA256SUMS
   python .github/scripts/release_manifest.py verify --manifest SHA256SUMS --dir .
   ```

5. Verify PyPI and smoke-test the immutable published package:

   ```bash
   python -m venv /tmp/adidt-release-verify
   /tmp/adidt-release-verify/bin/python -m pip install --no-cache-dir pyadi-dt==X.Y.Z
   /tmp/adidt-release-verify/bin/python -c \
     'import adidt, importlib.metadata as m; assert adidt.__version__ == m.version("pyadi-dt") == "X.Y.Z"'
   /tmp/adidt-release-verify/bin/adidtc --help
   ```

6. Verify the public documentation still serves successfully.

## Recover from partial failure

Release files on PyPI are immutable. Never move or reuse a version after any
artifact for it has been accepted by PyPI.

- **Validation/build failed before publication:** fix `main`, delete the failed
  remote tag only if neither PyPI nor a release artifact was published, rerun
  the dry run, and create a new annotated tag on the corrected commit.
- **PyPI upload partially succeeded:** rerun the failed jobs. Publishing uses
  `skip-existing`, so accepted files are retained and missing files can resume.
  Do not rebuild different bytes for the same version.
- **GitHub Release failed after PyPI succeeded:** rerun the failed job. The
  workflow creates a missing release or uploads artifacts to an existing one
  with `--clobber` and updates `SHA256SUMS`.
- **System-package attachment failed:** rerun the failed Debian or native-system
  package workflow for the original tag; do not retag.
- **Checksum manifest out of sync:** re-sync the release manifest using the
  helper script:
  ```bash
  python .github/scripts/release_manifest.py upsert-release --tag vX.Y.Z
  ```
- **A bad package was fully published:** keep the tag and release as an audit
  record, document the problem, bump to a new version, and publish a corrective
  release. PyPI versions cannot be replaced safely.
