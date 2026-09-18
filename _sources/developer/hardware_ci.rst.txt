Hardware CI
===========

The ``Hardware Tests`` workflow in ``.github/workflows/hardware-test.yml``
selects hardware through the labgrid coordinator. See
:doc:`hardware_validation` for the completed release qualification and
:doc:`runtime_overlay_validation` for the required overlay kernels.

Discovery and test selection
----------------------------

The workflow calls the reusable ``hw-matrix.yml`` workflow from
``tfcollins/labgrid-plugins`` with ``dynamic_mode: true``. Coordinator place
metadata supplies the runner routing; ``.github/supported-boards.yml`` filters
supported daughter-board tags. The current allowlist contains ``ad9081``,
``adrv9371``, ``adrv9009``, ``adrv9009zu11eg``, and ``daq3``. An allowlist entry
is not proof that matching hardware is available or validated.

Runs are triggered manually, on pushes to ``main``, nightly at 08:00 UTC,
and for pull requests carrying the ``hw-test`` label. The reusable workflow
owns discovery and scheduling. This repository does not define separate
``hw-direct`` and ``hw-coord`` jobs or route jobs using a static node manifest.

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
