from unittest.mock import Mock

import pytest

from pymmcore_plus import CMMCorePlus, DeviceProperty


def test_mmproperty(core: CMMCorePlus):
    for prop in core.iterProperties(as_object=True):
        assert prop.isValid()
        assert prop.dict()

        if prop.isReadOnly():
            with pytest.warns(UserWarning):
                prop.value = "asdf"


def test_property_callbacks(core: CMMCorePlus):
    prop = DeviceProperty("Camera", "Gain", core)
    mock = Mock()
    prop.connect_change_callback(mock)
    prop.value = 6
    mock.assert_called_once_with("6")
