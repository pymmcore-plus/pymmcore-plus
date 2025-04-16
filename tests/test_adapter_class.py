from pymmcore_plus import CMMCorePlus, Device, DeviceAdapter, DeviceType


def test_adapter_object(core: CMMCorePlus) -> None:
    # core.unloadAllDevices()
    for adapter in core.iterDeviceAdapters(as_object=True):
        assert adapter.name in repr(adapter)
        assert isinstance(adapter, DeviceAdapter)
        assert adapter.name
        assert adapter.core == core
        for ad in adapter.available_devices:
            assert isinstance(ad, Device)
            assert ad.type() is not DeviceType.Unknown
            assert ad.label == Device.UNASSIGNED
            assert ad.description()
            assert ad.library() == adapter.name
            assert ad.core == core
        # the load method and other stuff is hard to test without exceptions
        # need more specific tests
