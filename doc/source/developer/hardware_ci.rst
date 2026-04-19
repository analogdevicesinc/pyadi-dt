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

- **preflight** — runs on ``ubuntu-latest``, reads the node manifest
  (``.github/hw-nodes.json``), and queries the labgrid coordinator for
  advertised places.  It emits a JSON array of *available* nodes as
  the ``available_nodes`` job output.  If the coordinator is
  unreachable the TCP probe fails fast and ``available_nodes`` is
  ``[]`` — all downstream matrix legs then skip (green) instead of
  hanging on a hardware that is not powered up.
- **hw-direct** — a matrix job, one leg per available node, running
  on the self-hosted runner attached to that node
  (``runs-on: [self-hosted, <matrix.node.runner_label>]``).  Tests
  run without the coordinator, against a node-local labgrid YAML
  whose path is in the runner-level env var ``LG_DIRECT_ENV``.
- **hw-coord** — a matrix job, one leg per available node, all
  running on a single self-hosted runner labeled ``hw-coordinator``
  (typically on the coordinator host itself).  Each leg uses the
  committed ``env_remote_<place>.yaml`` that the manifest declares.

Every hw leg gates on the ``hardware-tests`` GitHub environment, so
PRs from forks require explicit maintainer approval before any
self-hosted runner is exercised.  The ``preflight`` job deliberately
does **not** gate on the environment — it only reads public
information, and keeping it ungated means fork PRs still get the
"hardware offline" skip signal instead of pausing indefinitely at the
approval step.

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

Coordinator-mode tests additionally require SSH key-auth from the
``hw-coordinator`` runner to the exporter host (for the
``MassStorageDriver`` SSH-proxy path) and write access to
``~/.cache/adidt/kernel/`` for the kernel image cache.

.. _hardware-tests-environment:

The ``hardware-tests`` environment
----------------------------------

The environment gate protects self-hosted runners from being
exercised by un-reviewed fork PRs.  To set it up (one-time, repo
admin):

**Via the GitHub UI** — *Settings → Environments → New environment*,
name it ``hardware-tests``, enable *Required reviewers*, and add at
least one maintainer.  Leave *Deployment branches* unrestricted.

**Via ``gh`` CLI** — equivalent scriptable form:

.. code-block:: bash

   gh api -X PUT \
     /repos/analogdevicesinc/pyadi-dt/environments/hardware-tests \
     -f "deployment_branch_policy=null" \
     -F "reviewers[][type]=User" \
     -F "reviewers[][id]=$(gh api /users/<maintainer> --jq .id)"

With the gate in place, a fork PR will show each hw job as
"Waiting for approval" under the ``hardware-tests`` environment; a
maintainer approves it from the PR page before the self-hosted
runners are scheduled.

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
  Fork PRs are held by the ``hardware-tests`` environment waiting
  for maintainer approval; check the PR page for the *Review
  deployments* button.
