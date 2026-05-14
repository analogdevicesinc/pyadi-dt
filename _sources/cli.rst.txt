Command Line Interface
======================

``adidtc`` is the CLI for pyadi-dt.  It provides commands for inspecting device
trees on live hardware, generating device tree source files from Vivado XSA
designs or board class configurations, and managing boot files on remote boards.

.. code-block:: bash

   pip install adidt          # core commands
   pip install "adidt[xsa]"   # adds xsa2dt and profile commands

Command Overview
----------------

Commands are grouped into three workflows:

Inspect device trees
~~~~~~~~~~~~~~~~~~~~~
Read, search, and modify device tree properties on live hardware (local or
remote over SSH) or from a ``.dtb`` file.

``prop``
   Get or set properties on a single node.  Supports lookup by node name or
   compatible string.

   .. code-block:: bash

      adidtc -c remote_sysfs -i 192.168.2.1 prop -cp adi,ad9361
      adidtc prop axi_ad9144_jesd compatible

``props``
   Like ``prop``, but supports hierarchical navigation through nested nodes by
   specifying multiple node names as a path.

   .. code-block:: bash

      adidtc props amba axi_ad9144_jesd -p compatible
      adidtc -c local_file -f devicetree.dtb props amba spi0

``deps``
   Analyze ``#include`` / ``/include/`` dependencies in a ``.dts`` file.
   Outputs a tree, GraphViz DOT, or JSON.

   .. code-block:: bash

      adidtc deps overlay.dts
      adidtc deps overlay.dts --format dot -o deps.dot

Generate device trees
~~~~~~~~~~~~~~~~~~~~~~
Produce ``.dts`` files from Vivado XSA designs, board class + solver configs,
or profile wizard exports.

``xsa2dt``
   Run the full 5-stage XSA pipeline (sdtgen, parse, build, merge, report).
   Requires ``sdtgen`` (lopper) on PATH.

   .. code-block:: bash

      adidtc xsa2dt -x design.xsa -c config.json -o out/
      adidtc xsa2dt -x design.xsa -c config.json --profile ad9081_zcu102 --lint

``gen-dts``
   Generate DTS from a board class and JSON config (optional pyadi-jif solver
   output).  No Vivado or XSA required.  Supported ``(board, platform)``
   combinations:

   - ``ad9081_fmc`` + ``zcu102``
   - ``ad9084_fmc`` + ``vpk180``

   .. code-block:: bash

      adidtc gen-dts -b ad9081_fmc -p zcu102 -c cfg.json -o design.dts
      adidtc gen-dts -b ad9084_fmc -p vpk180 -c cfg.json --compile

``jif clock``
   Apply pyadi-jif solver output to update clock-chip channel dividers in a
   device tree.  Supports ``local_file`` (edit a ``.dtb`` directly) and
   ``remote_sd`` (edit the board's SD card over SSH) contexts.  The live
   ``remote_sysfs`` path is not yet supported.

   .. code-block:: bash

      adidtc -c local_file -f devicetree.dtb -a arm64 jif clock -f solved.json
      adidtc -c remote_sd -i 192.168.2.1 jif clock -f solved.json --reboot

Manage boards and profiles
~~~~~~~~~~~~~~~~~~~~~~~~~~~
List supported boards, browse XSA profiles, and deploy boot files.

``kuiper-boards``
   List all boards from the ADI Kuiper Linux manifest with their device tree
   generation support status (full, profile_only, unsupported).

   .. code-block:: bash

      adidtc kuiper-boards
      adidtc kuiper-boards --status full
      adidtc kuiper-boards --json-output

``xsa-profiles``
   List built-in XSA board profiles available for ``xsa2dt --profile``.

   .. code-block:: bash

      adidtc xsa-profiles

``xsa-profile-show``
   Print the full JSON contents of a built-in XSA profile.

   .. code-block:: bash

      adidtc xsa-profile-show ad9081_zcu102

``sd-move``
   Switch the active reference design on a remote SD card.

   .. code-block:: bash

      adidtc -c remote_sd -i 192.168.2.1 sd-move daq2

``sd-remote-copy``
   Copy local boot files to a remote SD card over the network.

   .. code-block:: bash

      adidtc -c remote_sd -i 192.168.2.1 sd-remote-copy BOOT.BIN,system.dtb

Global Options
--------------

Every command inherits global options that control how ``adidtc`` connects to
the target:

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Option
     - Default
     - Description
   * - ``--context`` / ``-c``
     - ``local_sysfs``
     - Access method: ``local_sysfs`` (read ``/proc/device-tree``),
       ``remote_sysfs`` (SSH), ``local_sd`` / ``remote_sd`` (SD card mount),
       ``local_file`` (read a ``.dtb`` directly)
   * - ``--board`` / ``-b``
     - (none)
     - Board configuration for commands that need board-specific metadata
   * - ``--ip`` / ``-i``
     - ``192.168.2.1``
     - IP address for remote contexts
   * - ``--username`` / ``-u``
     - ``root``
     - SSH username for remote contexts
   * - ``--password`` / ``-w``
     - ``analog``
     - SSH password for remote contexts
   * - ``--arch`` / ``-a``
     - ``auto``
     - Target architecture (``arm``, ``arm64``, ``auto``)
   * - ``--filepath`` / ``-f``
     - ``devicetree.dtb``
     - Path to DTB file for ``local_file`` context
   * - ``--no-color`` / ``-nc``
     - off
     - Disable Rich formatting and color output

CLI Reference
-------------

Full auto-generated reference for all commands and options:

.. click:: adidt.cli.main:cli
   :prog: adidtc
   :nested: full
