import gc
import re
import weakref
from typing import Callable
from unittest.mock import Mock

import pytest
from pymmcore_plus import CMMCorePlus, DeviceProperty, DeviceType, PropertyType


def test_mmproperty(core: CMMCorePlus):
    for prop in core.iterProperties(as_object=True):
        assert prop.isValid()
        assert prop.dict()

        if prop.isReadOnly():
            with pytest.warns(UserWarning):
                prop.value = "asdf"


def test_iter_props(core: CMMCorePlus):
    for prop in core.iterProperties(property_name_pattern="(camera|test)s?"):
        assert "camera" in prop.name.lower() or "test" in prop.name.lower()

    for prop in core.iterProperties(property_name_pattern=re.compile("Test")):
        assert "Test" in prop.name

    for prop in core.iterProperties(property_type=PropertyType.String):
        assert prop.type() == PropertyType.String

    for prop in core.iterProperties(
        property_type={PropertyType.Integer, PropertyType.Float}
    ):
        assert prop.type() in {PropertyType.Integer, PropertyType.Float}

    for prop in core.iterProperties(is_read_only=True):
        assert prop.isReadOnly()

    for prop in core.iterProperties(has_limits=True):
        assert prop.hasLimits()

    for prop in core.iterProperties(is_sequenceable=True):
        assert prop.isSequenceable()

    for prop in core.iterProperties(
        property_type=PropertyType.String,
        device_type={DeviceType.Camera, DeviceType.Stage},
    ):
        assert prop.type() == PropertyType.String
        assert prop.deviceType() in {DeviceType.Camera, DeviceType.Stage}

    for prop in core.iterProperties(
        property_type=PropertyType.String, device_label="Cam"
    ):
        assert prop.type() == PropertyType.String
        assert "Cam" in prop.device


@pytest.mark.parametrize("cbtype", ["method", "func"])
def test_property_callbacks(cbtype, core: CMMCorePlus):
    prop = DeviceProperty("Camera", "Gain", core)
    mock = Mock()

    if cbtype == "method":

        class T:
            def method(self, *args):
                mock(*args)

        t = T()

    else:

        def t(*args):  # type: ignore
            mock(*args)

    r = weakref.ref(t)
    cnx: Callable = t.method if cbtype == "method" else t  # type: ignore

    # regular connection
    prop.valueChanged.connect(cnx)
    prop.value = 6
    mock.assert_called_once_with("6")

    # regular disconnection
    mock.reset_mock()
    prop.valueChanged.disconnect(cnx)
    prop.value = 4
    mock.assert_not_called()

    # reconnect
    mock.reset_mock()
    prop.valueChanged.connect(cnx)
    prop.value = 6
    mock.assert_called_once_with("6")

    # deleting the property object should *not* disconnect the callback
    mock.reset_mock()
    del prop
    gc.collect()
    gc.collect()
    core.events.propertyChanged.emit("Camera", "Gain", "4")
    mock.assert_called_once_with("4")

    # deleting the object itself *should* disconnect the callback
    if cbtype == "method":
        del t
        del cnx
        gc.collect()
        assert not gc.collect()

        assert r() is None
        mock.reset_mock()
        core.events.propertyChanged.emit("Camera", "Gain", "1")
        mock.assert_not_called()
