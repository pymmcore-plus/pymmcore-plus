import pytest

from pymmcore_plus import CMMCorePlus, Device, DeviceDetectionStatus, DeviceType


def test_device_object(core: CMMCorePlus):
    for device in core.iterDevices(as_object=True):
        device.wait()
        assert not device.isBusy()
        assert device.schema()
        assert device.description()
        lib = device.library()
        assert lib if device.type() is not DeviceType.Core else not lib
        assert device.name()
        assert repr(device)
        assert device.core is core
        assert device.isLoaded()

        if device.supportsDetection():
            assert device.detect() is not DeviceDetectionStatus.Unimplemented
        else:
            assert device.detect() is DeviceDetectionStatus.Unimplemented

        if device.type() is not DeviceType.Core:
            device.unload()
            assert not device.isLoaded()
            assert "NOT LOADED" in repr(device)


def test_device_load_errors(core: CMMCorePlus):
    dev = Device("Something", core)

    with pytest.raises(RuntimeError) as e:
        dev.load("NotAnAdapter", "prop")
    assert ("Adapter name 'NotAnAdapter' not in list of known") in str(e.value)

    with pytest.raises(RuntimeError) as e:
        dev.load("DemoCamera", "...")
    assert ("'...' not in devices provided by adapter 'DemoCamera'") in str(e.value)

    dev.load("DemoCamera", "DCam")

    with pytest.warns(UserWarning):
        dev.load("DemoCamera", "DCam")
