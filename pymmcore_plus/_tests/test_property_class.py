import pytest

from pymmcore_plus import CMMCorePlus


def test_mmproperty(core: CMMCorePlus):
    for prop in core.iterProperties(as_object=True):
        assert prop.isValid()
        assert prop.dict()

        if prop.isReadOnly():
            with pytest.warns(UserWarning):
                prop.value = "asdf"
