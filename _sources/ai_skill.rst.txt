AI Agent CLI Skill
==================

pyadi-dt includes a reusable `Agent Skill <https://agentskills.io/>`_ that
teaches compatible AI coding agents how to use the ``adidtc`` command-line
interface. The skill routes agents across all public commands, provides runnable
recipes, and adds safety rules for operations that can modify remote hardware or
SD-card contents.

Use the skill when asking an agent to:

- generate DTS output from a Vivado XSA or board configuration;
- inspect local DTBs or live device trees;
- analyze DTS include dependencies;
- discover supported Kuiper boards and XSA profiles; or
- stage boot files on a remote board.

The source is maintained in
`skills/pyadi-dt-cli/SKILL.md <https://github.com/analogdevicesinc/pyadi-dt/blob/main/skills/pyadi-dt-cli/SKILL.md>`_.
Detailed command recipes live in
`skills/pyadi-dt-cli/reference/commands.md <https://github.com/analogdevicesinc/pyadi-dt/blob/main/skills/pyadi-dt-cli/reference/commands.md>`_.

Install the skill
-----------------

Clone pyadi-dt, then run the bundled installer from the repository root:

.. code-block:: bash

   git clone https://github.com/analogdevicesinc/pyadi-dt.git
   cd pyadi-dt
   ./skills/pyadi-dt-cli/scripts/install.sh

The default ``all`` target creates symlinks in both of these Agent
Skills-compatible locations:

- ``~/.agents/skills/pyadi-dt-cli``
- ``~/.claude/skills/pyadi-dt-cli``

Install only one integration by passing its target explicitly:

.. code-block:: bash

   ./skills/pyadi-dt-cli/scripts/install.sh agents
   ./skills/pyadi-dt-cli/scripts/install.sh claude

The installer is idempotent when the destination already points to this
checkout. Start a new agent session after installation so the agent discovers
the skill.

How agents use it
-----------------

A compatible agent loads the skill when a request involves pyadi-dt, ``adidtc``,
XSA-to-DTS generation, device-tree inspection, Kuiper board discovery, or
SD-card deployment. It first inspects the installed CLI with
``adidtc --help`` and ``adidtc <command> --help`` rather than assuming flags.

The skill defaults to read-only contexts and requires a preview before changing
hardware. In particular, agents must run ``sd-move`` and ``sd-remote-copy`` with
``--dry-run --show`` and obtain explicit approval before the real operation.
Credentials must not be placed in commands, committed files, or reports.

For the human-oriented command reference and examples, see :doc:`cli`. For an
API integration that exposes pyadi-dt tools directly to AI assistants, see
:doc:`mcp_server`.

Example prompts
---------------

After restarting the agent, prompts can focus on the desired outcome rather
than reproducing CLI syntax:

- ``Generate and lint a DTS from design.xsa using the ad9081_zcu102 profile.``
- ``List the built-in XSA profiles and explain which one matches my carrier.``
- ``Inspect this DTB for nodes compatible with adi,ad9081 without modifying it.``
- ``Show a dry-run plan to copy BOOT.BIN and system.dtb to 192.168.2.1.``

The agent should report the exact commands executed, exit status, artifact
paths, validation performed, and whether hardware was only staged or actually
boot-tested.
