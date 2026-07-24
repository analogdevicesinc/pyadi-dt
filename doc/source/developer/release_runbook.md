# Release Operator Runbook

This runbook covers validation, publication, verification, and recovery for an
`adidt` release. The **Publish Release** workflow builds on manual dispatch but
publishes only when an annotated `v*` tag is pushed.

## One-time setup

### PyPI trusted publisher

Before the first release, sign in to PyPI and add a **pending trusted
publisher** with these exact values:

- PyPI project name: `adidt`
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

3. Run the hosted dry run from `main`. The candidate tag does **not** need to
   exist yet:

   ```bash
   gh workflow run release.yml --ref main -f tag=vX.Y.Z
   gh run watch --exit-status
   ```

   Confirm the validation, Python 3.10–3.13, build, wheel-install, and CLI
   smoke-test jobs pass. The GitHub Release and PyPI jobs must be skipped.
4. Confirm all required `main` workflows—including hardware and Debian—are
   green for the exact commit to be tagged.

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
2. Confirm the Debian workflow completed for the same tag and attached its
   `.deb` artifacts to the GitHub Release.
3. Verify the GitHub Release contains the wheel, source distribution, release
   notes, Debian artifacts, and `SHA256SUMS` manifest file.
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
   /tmp/adidt-release-verify/bin/python -m pip install --no-cache-dir adidt==X.Y.Z
   /tmp/adidt-release-verify/bin/python -c \
     'import adidt, importlib.metadata as m; assert adidt.__version__ == m.version("adidt") == "X.Y.Z"'
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
- **Debian attachment failed:** rerun the Debian workflow for the original tag;
  do not retag.
- **Checksum manifest out of sync:** re-sync the release manifest using the
  helper script:
  ```bash
  python .github/scripts/release_manifest.py upsert-release --tag vX.Y.Z
  ```
- **A bad package was fully published:** keep the tag and release as an audit
  record, document the problem, bump to a new version, and publish a corrective
  release. PyPI versions cannot be replaced safely.
