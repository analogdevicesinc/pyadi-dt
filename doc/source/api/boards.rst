Boards Module
=============

Board layout classes define the physical wiring between FPGA platforms and
ADI evaluation boards — SPI bus assignments, GPIO mappings, and DTC include
paths.

Board classes that support the unified model provide a ``to_board_model(cfg)``
method that produces a :class:`~adidt.model.board_model.BoardModel` from a
pyadi-jif solver configuration.  The model can be inspected and modified before
rendering to DTS via :class:`~adidt.model.renderer.BoardModelRenderer`.
See :doc:`model` for the full API.

Board Registry
--------------

Use ``get_board()`` to create board instances by name, or ``list_boards()``
to see all available boards:

.. code-block:: python

   from adidt.boards import get_board, list_boards

   print(list_boards())
   # ['ad9081_fmc', 'ad9082_fmc', ..., 'rpi']

   board = get_board("daq2", platform="zcu102")

Variant boards (AD9082, AD9083, ADRV9008, ADRV9025, ADRV937x) are
dynamically generated from their parent class with overridden
``PLATFORM_CONFIGS``.

.. automodule:: adidt.boards
   :members:
   :undoc-members:
   :show-inheritance:

Board Layout Base
-----------------

All board classes inherit from ``layout``, which provides shared
``__init__``, kernel path resolution, FPGA config validation, and DTS
rendering methods.

.. automodule:: adidt.boards.layout
   :members:
   :undoc-members:
   :show-inheritance:

Evaluation Boards
-----------------

DAQ2
~~~~

.. automodule:: adidt.boards.daq2
   :members:
   :undoc-members:
   :show-inheritance:

AD9081 FMC
~~~~~~~~~~

.. automodule:: adidt.boards.ad9081_fmc
   :members:
   :undoc-members:
   :show-inheritance:

AD9084 FMC
~~~~~~~~~~

.. automodule:: adidt.boards.ad9084_fmc
   :members:
   :undoc-members:
   :show-inheritance:

ADRV9009 FMC
~~~~~~~~~~~~

.. automodule:: adidt.boards.adrv9009_fmc
   :members:
   :undoc-members:
   :show-inheritance:

FMComms (AD9361/AD9363)
~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: adidt.boards.fmcomms_fmc
   :members:
   :undoc-members:
   :show-inheritance:

ADRV9361 Z7035
~~~~~~~~~~~~~~

.. automodule:: adidt.boards.adrv9361_z7035
   :members:
   :undoc-members:
   :show-inheritance:

ADRV9364 Z7020
~~~~~~~~~~~~~~

.. automodule:: adidt.boards.adrv9364_z7020
   :members:
   :undoc-members:
   :show-inheritance:

Raspberry Pi
~~~~~~~~~~~~

.. automodule:: adidt.boards.rpi
   :members:
   :undoc-members:
   :show-inheritance:
