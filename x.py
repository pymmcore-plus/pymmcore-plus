from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.metadata._dicts import SummaryMetaDictV1
from rich import print

core = CMMCorePlus()
core.loadSystemConfiguration()


# scope = model.Microscope.create_from_core(core)
# print(scope)


meta = SummaryMetaDictV1.from_core(core, {})
print(meta)
