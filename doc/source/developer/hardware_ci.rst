Hardware CI
===========

The ``Hardware Tests`` workflow in ``.github/workflows/hardware-test.yml``
selects hardware through the labgrid coordinator. See
:doc:`hardware_validation` for the completed release qualification and
:doc:`runtime_overlay_validation` for the required overlay kernels.

Discovery and test selection
----------------------------

The workflow calls a local copy of ``hw-matrix.yml`` (upstream
``tfcollins/labgrid-plugins`` commit
``3f6cd9321f2d54edf2110f1d91a3af582ea368d7``) with ``dynamic_mode: true``.
The local addition prepares ordinary kernels **before** ``acquire-place``;
the upstream pre-pytest hook runs after acquisition and cannot do this safely.
Coordinator place
metadata supplies the runner routing; ``.github/supported-boards.yml`` filters
supported daughter-board tags. The current allowlist contains ``ad9081``,
``adrv9371``, ``adrv9009``, ``adrv9009zu11eg``, and ``daq3``. An allowlist entry
is not proof that matching hardware is available or validated.

Runs are triggered manually, on pushes to ``main``, nightly at 08:00 UTC,
and for pull requests carrying the ``hw-test`` label. The reusable workflow
owns discovery and scheduling. The inherited direct/coordinator jobs remain
disabled; routing uses dynamic metadata rather than a static node manifest.

Each selected leg receives ``BOARD``, ``CARRIER``, ``LG_ENV``, and
``LG_COORDINATOR``. Its test command selects:

* Full-DTB tests matching ``test/hw/*${BOARD}*${CARRIER}*_hw.py``.
* Overlay tests matching ``test/hw/xsa/test_*${BOARD}*${CARRIER}*_overlay.py``.

PetaLinux tests are excluded from this workflow's selection. An empty selection
fails. After pytest, ``check_hardware_results.py`` requires passing JUnit
results without failures or errors; an all-skipped run cannot qualify hardware.

.. _runner-registration:

Runner preparation
------------------

Register the self-hosted runner and give it the label selected by the place's
coordinator ``runner`` tag. It needs access to the coordinator and exporter,
the board's boot artifacts, and the appropriate FPGA tools.

``.github/scripts/install-adidt-venv.sh`` installs the checkout with ``dev``
extras into ``~/.cache/adidt-ci/adidt-venv``. It also installs the AD9371
clock-model requirements and exposes the supported Vivado 2025.1 ``sdtgen``
launcher in that environment. Missing tools or imports fail setup before
hardware acquisition.

``.github/scripts/prepare-hardware-env.sh`` then:

#. Loads optional board-specific artifact settings from
   ``~/.config/pyadi-dt/hardware/$BOARD-$CARRIER.env``. Override the directory
   with ``ADIDT_HARDWARE_CONFIG_DIR``.
#. Sanitizes ``PATH`` and verifies GNU ``as``, labgrid, pytest, and ``sdtgen``.
#. Prepares a private labgrid environment from the live place tags.
   TFTP deployment disables SD autoboot; ZynqMP deployment registers the
   pinned production JTAG strategy and accepts either Ethernet port.

Keep operational labgrid environments private. The workflow passes
``PYADI_BUILD_TOKEN`` for private dependency access. Optional Prism upload is
controlled by ``PRISM_UPLOAD_ENABLED`` and uses the explicitly passed
``PRISM_EMAIL`` and ``PRISM_PASSWORD`` secrets. These values are not test
artifacts.

Prepared CIM kernels
--------------------

The ``dev`` extra no longer installs private ``pyadi-build``. Kernel compilation,
Zynq ``uImage`` packaging, source/toolchain pinning, and build caches belong to
`CIM <https://github.com/tfcollins/cim>`_, not pyadi-dt. The old
``test/hw/2023_R2.yaml``, ``ADIDT_KERNEL_CACHE`` and
``ADIDT_KERNEL_CACHE_DIR`` are no longer used. Existing cache directories are
not deleted; explicitly select a known-good image if you need to reuse one.
``PYADI_BUILD_TOKEN`` remains the reusable workflow's credential name for
labgrid-plugins access; it is not a kernel build dependency.

Prepare **only the platform needed by the selected tests**, before acquiring a
place. An installed CIM executable and an explicit, reviewed manifest source
and full Git commit are required for builds (there is no implicit ``main`` or
package installation). Install the host build dependencies listed in the CIM
target's ``os-dependencies.yml`` separately. For example, for ZC706:

.. code-block:: bash

   # Set these to the reviewed manifest repository and full commit containing
   # adi-linux-2023-r2-zynq (or adi-linux-2023-r2-zynqmp for ZynqMP).
   : "${CIM_MANIFEST_SOURCE:?set the reviewed CIM manifest repository}"
   : "${CIM_MANIFEST_COMMIT:?set its full reviewed Git commit SHA}"
   python .github/scripts/prepare_cim_kernel.py \
       --platform zynq --cim /path/to/installed/cim \
       --source "$CIM_MANIFEST_SOURCE" --version "$CIM_MANIFEST_COMMIT" \
       --workspace "$HOME/cim-kernels/$CIM_MANIFEST_COMMIT-zynq" \
       > /tmp/adidt-kernel.env
   # Only source the output if preparation succeeded.
   source /tmp/adidt-kernel.env

The helper uses ``cim init``, ``cim makefile``, and ``make sdk-build``. It refuses
to overwrite a workspace; to reuse its results, export the existing manifest
path instead of rebuilding. It validates the handoff before emitting a
shell-quoted export. It does not install CIM, reserve boards, or modify runner
configuration. Run the command with ``set -e`` or explicitly check its exit
status before sourcing its output. Prepared-image and disabled modes do not
invoke CIM and do not require source/version/workspace arguments.

For persistent runners, put the resulting export in the existing per-board
``$BOARD-$CARRIER.env`` file. The matrix runs
``prepare-hardware-kernels.sh`` before acquisition, loads that same file, and
validates explicit ordinary images/manifests. Without them it builds using
``CIM_MANIFEST_SOURCE``, ``CIM_MANIFEST_COMMIT`` (a full immutable SHA), and
``ADIDT_CIM_EXECUTABLE`` (an installed absolute executable path recommended).
The default manifest source is ``https://github.com/tfcollins/cim.git`` at
``d4dd5677cb965b3ee4085041535154483f3daecf``. Override settings through the
runner environment or per-board file; CIM itself must be installed separately.
No packages are installed and no mutable branch is silently selected. Missing
settings fail before acquisition. New workspaces are run-scoped under
``RUNNER_TEMP``; for cache reuse provision a persistent manifest explicitly.
Fabric-only legs do not build ARM kernels; disabled mode and image overrides
bypass CIM entirely. Do not build on disk-constrained runners: stage verified
CIM artifacts built on another host and update their absolute image paths and
checksums, or explicitly select a boot-ready external image.

Runtime-overlay tests still require their separately qualified modular kernels
and matching modules; the ordinary CIM targets do not qualify overlays. The
pre-acquisition step refuses an enabled overlay leg without an explicit
overlay image (or a qualified generic image override). Existing
``ADIDT_OVERLAY_KERNEL_IMAGE_ZYNQ`` and module settings are not rewritten.

The handoff is a runner-local JSON object with these required fields:

.. code-block:: json

   {
     "schema_version": 1,
     "platform": "zynq",
     "kernel_image": "/absolute/path/to/uImage",
     "sha256": "<64 hexadecimal characters>"
   }

CIM additionally records source, toolchain, configuration and packaging
provenance. pyadi-dt allows extra provenance fields and checks the schema,
expected platform, non-empty regular image file, absolute image path and
SHA-256. Keep the manifest and its image together on the runner; copying just
the JSON does not relocate the absolute image path. Do not modify images while
tests are running. No consumer-side packaging or implicit cache fallback occurs.

Selection order for each platform is:

#. ``ADIDT_KERNEL_IMAGE_ZYNQ`` / ``ADIDT_KERNEL_IMAGE_ZYNQMP``: explicit prebuilt
   image, still honored when kernel replacement is otherwise disabled.
#. ``ADI_XSA_BUILD_KERNEL=0`` (also ``false`` or ``no``): retain the existing
   kernel and return no replacement, ignoring CIM manifests.
#. ``ADIDT_KERNEL_ARTIFACTS_ZYNQ`` / ``ADIDT_KERNEL_ARTIFACTS_ZYNQMP``:
   validate and use the manifest image; missing/invalid input is a hard error.

Hardware collection preflights the selected module profiles before labgrid
fixtures run, while ``--collect-only`` remains usable without artifacts.
Overlay-only image overrides take priority for overlay modules, not ordinary
full-DTB tests. When manually reserving a place outside pytest, perform kernel
preparation/validation before the explicit ``labgrid-client acquire`` command.

.. _exporter-systemd:

Exporter service
----------------

Exporters publish the serial, power, JTAG, and other resources used by the
coordinator. The repository's installation convention uses one
``labgrid-exporter.service`` per host and ``/etc/labgrid/exporter.yaml``.
See :doc:`labgrid_exporter` for installation and service operation.

Generated-DTB deployment
------------------------

A successful stock-image boot does not qualify a generated tree. Tests stamp
the generated DTB and verify its unique marker in Linux. TFTP tests require a
strategy that consumes the staged files; recovery strategies that boot only
the existing SD tree are unsuitable for those tests.

The ZU11EG test uses production JTAG bootstrap followed by U-Boot's serial
S-record loader. It verifies the complete RAM payload CRC, the marker in both
U-Boot and Linux, four online CPUs, both PHYs, JESD DATA, and RX DMA.
See :doc:`hardware_validation` for prerequisites and a local test command.

For runtime overlays, use the matching modular kernels, module bundles, and
base trees described in :doc:`runtime_overlay_validation`. Installing
``pyadi-dt`` does not update a board's kernel. Overlay tests verify live-tree
application and removal as well as JESD and DMA on each reload.

Local runs and evidence
-----------------------

Use the same checkout and prepared environment as CI. From a Bash shell at the
repository root, set ``LG_ENV`` to an existing private configuration for the
selected place, then run:

.. code-block:: bash

   export VENV_DIR="$HOME/.cache/adidt-ci/adidt-venv"
   export LG_COORDINATOR=10.0.0.41:20408
   export BOARD=adrv9009 CARRIER=zc706
   source .github/scripts/prepare-hardware-env.sh
   "$VENV_DIR/bin/labgrid-client" -p nemo acquire
   trap '"$VENV_DIR/bin/labgrid-client" -p nemo release' EXIT
   "$VENV_DIR/bin/python" -m pytest -p no:genalyzer -v -s \
       test/hw/xsa/test_adrv9009_zc706_overlay.py \
       --junitxml=/tmp/adrv9009-overlay.xml
   "$VENV_DIR/bin/python" .github/scripts/check_hardware_results.py \
       /tmp/adrv9009-overlay.xml

The shared board fixture powers down the board on teardown, including failed
boots. Retain failed reports as well as passing evidence. The workflow collects
generated DTS/DTB/DTBO files, kernel and serial logs, and JUnit reports. Record
the tested commit and artifact checksums alongside those results.

.. _local-dts-diff:

Local DT-emission parity
------------------------

Run the System-API parity checks before deploying changed device wiring:

.. code-block:: bash

   python -m pytest test/devices/test_system_adrv9371_zc706_dts_parity.py \
       test/devices/test_system_ad9081_dts_parity.py

Reference fixtures live under ``test/devices/fixtures``. Refresh a fixture only
from a reviewed reference or verified generated tree; a parity comparison
alone does not establish live hardware coverage.

Troubleshooting
---------------

* **No matching leg:** inspect the reusable workflow's discovery output,
  coordinator daughter-board/carrier tags, runner routing, and the allowlist.
* **Empty or skipped-only test results:** check filename selection, pytest
  feature markers, and missing prerequisites. Do not treat this as a pass.
* **Wrong tree after boot:** inspect the prepared strategy and staged-file
  consumption, and retain the marker mismatch. Do not substitute a stock boot.
* **ZU11EG JTAG reaches the wrong host:** verify exporter resolution.
  ``ADIDT_JTAG_HOST`` overrides JTAG resource hosts for the test process and
  restores them during teardown.
* **Overlay rejected or modules busy:** check the kernel/module match and
  topology teardown sequence. The harness does not force module removal or
  bypass the JESD notifier.
* **FMCDAQ3 serial command truncation:** the BootFabric fixture paces writes at
  a minimum of 2 ms per byte to accommodate UART Lite's receive FIFO.
