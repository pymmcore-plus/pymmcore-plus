from pymmcore_plus import Adapter, CMMCorePlus
from pymmcore_plus.core._adapter import AvailableDevice


def test_adapter_object(core: CMMCorePlus) -> None:
    core.unloadAllDevices()
    for adapter in core.iterAdapters(as_object=True):
        assert adapter.name in repr(adapter)
        assert isinstance(adapter, Adapter)
        assert adapter.name
        assert adapter.core == core
        for ad in adapter.available_devices:
            assert isinstance(ad, AvailableDevice)
            assert ad.core == core
        # the load method and other stuff is hard to test without exceptions
        # need more specific tests
