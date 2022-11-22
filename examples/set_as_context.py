from pymmcore_plus import CMMCorePlus

core = CMMCorePlus.instance()

# set some state temporarily
with core.setContext(autoShutter=False):
    assert not core.getAutoShutter()
    # do other stuff

assert core.getAutoShutter()
