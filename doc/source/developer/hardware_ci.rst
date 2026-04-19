Hardware CI
===========

Hardware tests under ``test/hw/`` are driven by GitHub Actions through
the ``Hardware Tests`` workflow (``.github/workflows/hardware-test.yml``).
This page is the reference for setting up the runners, secrets, and
per-node configuration that workflow depends on — plus the recipe for
onboarding a new hardware node.

How it works
------------

The workflow has three jobs:

- **preflight** — runs on the ``hw-coordinator`` self-hosted runner
  (the only host with a route to the private-lab labgrid coordinator),
  reads the node manifest (``.github/hw-nodes.json``), and queries the
  coordinator for advertised places.  It emits a JSON array of
  *available* nodes as the ``available_nodes`` job output.  If the
  coordinator is unreachable the TCP probe fails fast and
  ``available_nodes`` is ``[]`` — all downstream matrix legs then skip
  (green) instead of hanging on hardware that is not powered up.
- **hw-direct** — a matrix job, one leg per available node, running
  on the self-hosted runner attached to that node
  (``runs-on: [self-hosted, <matrix.node.runner_label>]``).  Tests
  run without the coordinator, against a node-local labgrid YAML
  whose path is in the runner-level env var ``LG_DIRECT_ENV``.  When
  ``LG_DIRECT_ENV`` is unset on a runner the job skips all work and
  exits green — add the env entry in ``~/actions-runner/.env`` to
  light up direct-mode on that node.
- **hw-coord** — a matrix job, one leg per available node, running
  on the **same per-node runner as hw-direct** (label
  ``hw-<place>``).  Each leg uses the committed
  ``env_remote_<place>.yaml`` from the manifest and talks to the
  labgrid coordinator via ``LG_COORDINATOR`` — so pytest exercises
  the coordinator code path while the XSA toolchain (Vivado's
  sdtgen, xsct) and kernel build artifacts already present on the
  per-node runner are used in place.  The ``hw-coordinator`` runner
  itself carries only the preflight job.

Fork-PR protection is handled by GitHub Actions' built-in workflow
approval gate rather than a custom ``environment:``.  Under *Settings
→ Actions → General → Approval for outside collaborators*, workflows
triggered by fork PRs require a maintainer to click "Approve and run"
before any self-hosted runner is scheduled.  Same-repo PRs, pushes to
``main``, and ``workflow_dispatch`` are always trusted and run
directly.

Node manifest
-------------

``.github/hw-nodes.json`` is the single source of truth for per-node
CI configuration:

.. code-block:: json

   [
     {
       "place": "bq",
       "runner_label": "hw-bq",
       "env_remote": "env_remote_bq.yaml",
       "tests": ["test/hw/test_adrv9371_zc706_hw.py"]
     },
     {
       "place": "mini2",
       "runner_label": "hw-mini2",
       "env_remote": "env_remote_mini2.yaml",
       "tests": [
         "test/hw/test_ad9081_zcu102_xsa_hw.py",
         "test/hw/test_ad9081_zcu102_system_hw.py"
       ]
     }
   ]

Field reference:

- ``place`` — the labgrid coordinator place name.  Must match what
  the exporter registers (``labgrid-client places`` on the
  coordinator host).
- ``runner_label`` — the extra label on the self-hosted runner
  physically attached to the board.  Convention: ``hw-<place>``.
- ``env_remote`` — the committed env YAML (at the repo root) used by
  the ``hw-coord`` matrix leg.  Must use ``RemotePlace`` only — no
  local paths, no credentials, no serial device names.
- ``tests`` — list of ``pytest`` targets (test files) to run for
  this node, used verbatim in both ``hw-direct`` and ``hw-coord``.

Adding a new hardware node
--------------------------

One-time setup:

1. Stand up an exporter that registers a new place ``<name>`` with
   the coordinator at ``10.0.0.41:20408``.  Verify with
   ``labgrid-client -x 10.0.0.41:20408 places``.
2. Register a new self-hosted runner with labels
   ``self-hosted,hw-<name>`` on the host physically attached to the
   board (see :ref:`runner-registration` below).
3. Author a node-local labgrid YAML on the runner host — typically
   ``~/ci/lg_direct.yaml`` — that describes the exporter resources
   directly (no ``RemotePlace``).  Reference
   ``lg_adrv9371_zc706_tftp.yaml`` on ``bq`` for a worked example.
4. Put ``LG_DIRECT_ENV=/home/<user>/ci/lg_direct.yaml`` in
   ``~/actions-runner/.env`` on the runner host.  The runner picks
   this up automatically on the next job.
5. Author a ``env_remote_<name>.yaml`` at the repo root using
   ``RemotePlace`` only; commit it.
6. Append one entry to ``.github/hw-nodes.json`` with the new place,
   runner label, env_remote path, and test list.  No workflow edits
   needed.

That's it — the next workflow run picks up the new node automatically
via ``fromJSON(needs.preflight.outputs.available_nodes)``.

.. _runner-registration:

Self-hosted runner registration
-------------------------------

Prerequisites (one-time, repo-admin only):

- GitHub CLI (``gh``) installed locally, authenticated with a repo
  admin account for ``analogdevicesinc/pyadi-dt``.

Generate a one-use registration token:

.. code-block:: bash

   gh api -X POST \
     /repos/analogdevicesinc/pyadi-dt/actions/runners/registration-token

Copy the ``token`` value from the response.

On the target host:

.. code-block:: bash

   mkdir -p ~/actions-runner && cd ~/actions-runner
   # Pick the latest from https://github.com/actions/runner/releases
   curl -O -L https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
   tar xzf actions-runner-linux-x64-2.319.1.tar.gz
   ./config.sh --url https://github.com/analogdevicesinc/pyadi-dt \
               --token <TOKEN> \
               --labels self-hosted,hw-<place>
   sudo ./svc.sh install && sudo ./svc.sh start

For the runner on the coordinator host (``10.0.0.41``), use
``--labels self-hosted,hw-coordinator``.  That is the only label the
workflow hardcodes; every other ``hw-*`` label flows from the
manifest.

Populate the runner-level env file so the direct-mode job can find
the node-local labgrid YAML:

.. code-block:: bash

   echo "LG_DIRECT_ENV=/home/$USER/ci/lg_direct.yaml" >> ~/actions-runner/.env
   sudo ./svc.sh stop && sudo ./svc.sh start

(The ``hw-coordinator`` runner does not need ``LG_DIRECT_ENV`` — it
only runs ``hw-coord`` legs, which use the committed
``env_remote_*.yaml`` files.)

System-tool prerequisites on each hw-node runner:

.. code-block:: bash

   sudo apt-get install -y device-tree-compiler cpp u-boot-tools
   # For ZynqMP nodes:
   pip install --user xilinx-sdt-gen
   # For ZCU102/AD9081 (USB SD-mux mode):
   sudo apt-get install -y usbsdmux

On **every** hw-node runner (including the coordinator host), the
workflow uses `uv <https://github.com/astral-sh/uv>`_ to build two
persistent venvs under ``~/.cache/adidt-ci/``: one for
``labgrid-client`` on the coordinator host, and one holding an
editable ``pip install -e ".[dev]"`` of adidt on every runner.
``.github/scripts/bootstrap-uv.sh`` curl-installs ``uv`` into
``~/.local/bin`` on first use, so no distro Python packaging is
required — only ``curl`` and a working ``python3`` interpreter (both
present on stock Debian/Ubuntu).

Coordinator-mode tests additionally require SSH key-auth from the
``hw-coordinator`` runner to the exporter host (for the
``MassStorageDriver`` SSH-proxy path) and write access to
``~/.cache/adidt/kernel/`` for the kernel image cache.

Fork-PR approval gate
---------------------

Fork-PR workflows are held by GitHub's built-in approval gate
configured at *Settings → Actions → General → Approval for outside
collaborators*.  Pick *Require approval for first-time contributors*
(or stricter) so fork-PR runs pause until a maintainer clicks
*Approve and run* in the PR's Actions tab.  No custom
``environment:`` is needed on the workflow side.

Private-repo dependency access
------------------------------

The ``[dev]`` extras in ``pyproject.toml`` include
``pyadi-build @ git+https://github.com/tfcollins/pyadi-build.git``,
which currently points at a private repo.  For CI to ``uv pip
install`` it, scope a fine-grained PAT to the private repo and store
it as a repository secret.

1. Create a fine-grained PAT at
   `<https://github.com/settings/tokens?type=beta>`_:

   - *Token name*: ``pyadi-dt-ci-pyadi-build-read``
   - *Resource owner*: the org/user that owns the private dependency
     (here: ``tfcollins``)
   - *Repository access*: **Only select repositories** → pick
     ``tfcollins/pyadi-build`` (and any other private deps).
   - *Repository permissions* → **Contents: Read-only**.

2. Store it at repository scope.  Fork PRs don't see repo secrets
   until a maintainer approves via the built-in workflow approval
   gate, so the PAT stays protected without any environment
   indirection.

   .. code-block:: bash

      # Repo-scoped secret — visible to trusted (non-fork) runs,
      # and to fork-PR runs only after maintainer "Approve and run".
      gh secret set PYADI_BUILD_TOKEN \
          --repo analogdevicesinc/pyadi-dt \
          --body 'github_pat_...'

   (Or via the GitHub UI: *Settings → Secrets and variables →
   Actions → New repository secret*.)

The install step reads ``secrets.PYADI_BUILD_TOKEN`` and exports it
as a process-local ``GIT_CONFIG_COUNT`` / ``GIT_CONFIG_KEY_0`` /
``GIT_CONFIG_VALUE_0`` triple that rewrites ``https://github.com/``
to ``https://x-access-token:<token>@github.com/`` for the duration
of that step.  The secret is never written to the runner's
``~/.gitconfig`` so it doesn't leak to later jobs.

Troubleshooting
---------------

**All hw jobs skip on every run.**
  Preflight is marking everything unavailable.  Check the preflight
  job logs for "Coordinator ... unreachable" or the places listing.
  Try ``labgrid-client -x 10.0.0.41:20408 places`` from any host.

**One node's jobs skip while others run.**
  The corresponding exporter is not advertising its place to the
  coordinator.  SSH to that node, restart the exporter, and verify
  the place shows up in ``labgrid-client places``.

**``hw-direct`` fails with "LG_DIRECT_ENV is not set".**
  The runner's ``~/actions-runner/.env`` does not define
  ``LG_DIRECT_ENV``, or the file path it points at does not exist.
  Edit the file and restart the runner service.

**``hw-coord`` fails with "No such file" on the env yaml.**
  The manifest entry's ``env_remote`` path points at a file that is
  not committed at the repo root.  Either commit the YAML or fix the
  manifest entry.

**PR from a fork never runs hw jobs.**
  Fork PRs pause on GitHub's built-in workflow approval gate.
  Open the PR's Actions tab and click *Approve and run* to release
  the jobs.
