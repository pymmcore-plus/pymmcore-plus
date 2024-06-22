from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.metadata import summary_metadata
from rich import print

core = CMMCorePlus()
core.loadSystemConfiguration()


# scope = model.Microscope.create_from_core(core)
# print(scope)


meta = summary_metadata(core, {})
print(meta)
