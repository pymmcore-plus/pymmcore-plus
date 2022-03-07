from pymmcore_plus import CMMCorePlus


def test_mmproperty(core: CMMCorePlus):
    for device in core.iterDevices(as_object=True):
        assert device.isLoaded()
        assert device.schema()
        assert repr(device)
