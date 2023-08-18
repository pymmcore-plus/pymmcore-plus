from pathlib import Path

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.model.device import Microscope
from rich import print

core = CMMCorePlus()
core.loadSystemConfiguration()
cfg = Path(core._mm_path) / "MMConfig_demo.cfg"
cfg = cfg.read_text()

scope = Microscope.create_from_core(core)
print(scope.save("asdf"))
