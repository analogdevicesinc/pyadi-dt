"""adidt — device-centric device-tree composition for ADI hardware."""

__version__ = "0.0.1"

from adidt.dt import dt as dt
from adidt.model.board_model import BoardModel as BoardModel
from adidt.model.renderer import BoardModelRenderer as BoardModelRenderer

# Device-centric composition API.
from adidt import devices as devices
from adidt import eval as eval
from adidt import fpga as fpga
from adidt.system import System as System
