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

.. automodule:: adidt.boards
   :members:
   :undoc-members:
   :show-inheritance:

Board Layout Base
-----------------

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

ADRV9009 PCB-Z
~~~~~~~~~~~~~~

.. automodule:: adidt.boards.adrv9009_pcbz
   :members:
   :undoc-members:
   :show-inheritance:

ADRV9009 ZU11EG
~~~~~~~~~~~~~~~

.. automodule:: adidt.boards.adrv9009_zu11eg
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
