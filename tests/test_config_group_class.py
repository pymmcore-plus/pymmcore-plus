import pytest
from pymmcore_plus import CMMCorePlus, ConfigGroup, Configuration


def test_config_group():
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    group = core.getConfigGroupObject("Channel")
    assert group.exists()
    assert group.name == "Channel"
    assert group.core is core

    assert len(group) == 4
    assert isinstance(repr(group), str) and "ConfigGroup" in repr(group)
    assert isinstance(str(group), str) and "Channel" in str(group)

    assert set(group) == {"DAPI", "FITC", "Cy5", "Rhodamine"}
    assert "DAPI" in group

    dapi = group["DAPI"]
    assert isinstance(dapi, Configuration)

    del group["DAPI"]
    assert "DAPI" not in group
    with pytest.raises(KeyError, match="Group 'Channel' does not have a config 'DAPI'"):
        group["DAPI"]


def test_set_config():
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    group = core.getConfigGroupObject("Channel")

    group.setConfig("DAPI")
    group.wait()
    assert group.getCurrentConfig() == "DAPI"

    obj = list(group.getCurrentConfig(as_object=True))
    assert obj[0] == ("Dichroic", "Label", "400DCLP")
    assert core.getProperty("Dichroic", "Label") == "400DCLP"

    group.setConfig("FITC")
    group.wait("FITC")
    assert group.getCurrentConfig() == "FITC"
    assert core.getProperty("Dichroic", "Label") == "Q505LP"

    assert group.getCurrentConfigFromCache() == "FITC"


def test_config_group_create():
    core = CMMCorePlus()
    NAME1 = "MyGroup"
    with pytest.raises(KeyError, match="Configuration group"):
        group = core.getConfigGroupObject(NAME1)

    group = core.getConfigGroupObject(NAME1, allow_missing=True)
    assert not group.exists()
    group.create()
    assert group.exists()
    assert not group
    assert len(group) == 0
    assert not list(group.iterDeviceProperties())

    group.delete()
    assert not group.exists()

    group["Config"] = ("Dichroic", "Label", "Q585LP")
    group["Config"] = ("Emission", "Label", "Chroma-HQ700")
    # setting  as a sequence must be len 3
    with pytest.raises(ValueError, match="Expected a 3-tuple"):
        group["Config"] = (
            "Emission",
            "Label",
        )

    assert "Config" in group
    assert list(group["Config"]) == [
        ("Dichroic", "Label", "Q585LP"),
        ("Emission", "Label", "Chroma-HQ700"),
    ]

    group["Config"] = {
        ("Dichroic", "Label"): "400DCLP",
        ("Emission", "Label"): "Chroma-HQ700",
        ("Excitation", "Label"): "Chroma-HQ570",
    }

    # setting as a dict must be a dict of 2-tuples -> str
    with pytest.raises(ValueError, match="Expected a dict of {\\(deviceLabel"):
        group["Config"] = {("Dichroic",): "400DCLP"}

    assert list(group["Config"]) == [
        ("Dichroic", "Label", "400DCLP"),
        ("Emission", "Label", "Chroma-HQ700"),
        ("Excitation", "Label", "Chroma-HQ570"),
    ]

    group["Config"] = group["Config"]  # set directly with a config object
    assert list(group["Config"]) == [
        ("Dichroic", "Label", "400DCLP"),
        ("Emission", "Label", "Chroma-HQ700"),
        ("Excitation", "Label", "Chroma-HQ570"),
    ]

    with pytest.raises(ValueError, match="Expected a 3-tuple"):
        group["Bad"] = 1
    assert "Bad" not in group

    group.renameConfig("Config", "NewConfig")
    assert list(group["NewConfig"]) == [
        ("Dichroic", "Label", "400DCLP"),
        ("Emission", "Label", "Chroma-HQ700"),
        ("Excitation", "Label", "Chroma-HQ570"),
    ]
    assert "Config" not in group
    with pytest.raises(KeyError):
        group.renameConfig("asdfdsf", "asdfsd")

    group.rename("NewGroupName")
    assert group.name == "NewGroupName"
    assert "NewGroupName" in core.getAvailableConfigGroups()
    assert NAME1 not in core.getAvailableConfigGroups()


def test_group_consistency():
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    group = core.getConfigGroupObject("MyGroup", allow_missing=True)
    group.create()
    assert group.is_consistent  # empty group is consistent
    group["Config"] = ("Dichroic", "Label", "Q585LP")
    assert group.is_consistent  # 1 group is consistent
    group["Config2"] = ("Dichroic", "Label", "Q585LP")
    group["Config3"] = ("Dichroic", "Label", "400DCLP")
    assert group.is_consistent  # 2 groups with same property
    group["Config4"] = ("Excitation", "Label", "Chroma-HQ570")
    assert not group.is_consistent  # config4 is broken


def test_iter_config_group():
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    for i in core.iterConfigGroups():
        assert isinstance(i, ConfigGroup)
