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
            dev = ad.load(ad.device_name)
            # we can't do a plain `in` because they are not the same object
            assert dev.name() in [x.name() for x in adapter.loaded_devices]
            dev.unload()
            assert not adapter.loaded_devices
        adapter.unload()
