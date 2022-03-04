import pytest

import pymmcore_plus


@pytest.fixture(params=["QSignal", "psygnal"], scope="function")
def core(request):
    core = pymmcore_plus.CMMCorePlus()
    if request.param == "psygnal":
        core.events = pymmcore_plus.CMMCoreSignaler()
        core._callback_relay = pymmcore_plus.core._mmcore_plus.MMCallbackRelay(
            core.events
        )
        core.registerCallback(core._callback_relay)
    if not core.getDeviceAdapterSearchPaths():
        pytest.fail(
            "To run tests, please install MM with `python -m pymmcore_plus.install`"
        )
    core.loadSystemConfiguration()
    return core
