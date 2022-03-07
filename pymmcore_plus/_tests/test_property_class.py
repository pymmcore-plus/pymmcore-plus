from pymmcore_plus import CMMCorePlus, MMProperty, iter_device_props


def test_mmproperty(core: CMMCorePlus):
    for dp in iter_device_props(core):
        prop = MMProperty(*dp, mmcore=core)
        assert prop.isValid()
        assert prop.dict()
