from __future__ import annotations

from pathlib import Path

import pytest
from pymmcore_plus import CMMCorePlus, DeviceType, find_micromanager
from pymmcore_plus.model import CoreDevice, Device, Microscope


def test_model_create() -> None:
    model = Microscope()
    assert model.core_device
    assert not model.devices
    assert not list(model.filter_devices("NotADevice"))
    assert not list(model.filter_devices(device_type="Camera"))
    assert not list(model.filter_devices(device_type=DeviceType.Camera))
    assert next(model.filter_devices(device_type=DeviceType.Core)) == model.core_device


def test_model_from_core() -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    model = Microscope.create_from_core(core)
    assert model.devices
    assert model.available_devices
    assert model.available_serial_devices
    assert not model.assigned_com_ports
    hash(model.devices[0])
    hash(model.core_device)
    hash(model.available_devices[0])

    model2 = Microscope()
    model2.update_from_core(core)

    assert model == model2


def test_model_from_config() -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    config = Path(__file__).parent / "local_config.cfg"
    assert Microscope.create_from_config(config).devices


def non_empty_lines(path: Path) -> list[str]:
    return [
        ln
        for line in path.read_text().splitlines()
        if (ln := line.strip()) and not ln.startswith("#")
    ]


if not (mm_path := find_micromanager()):
    raise RuntimeError("Could not find Micro-Manager, please run `mmcore install`")


@pytest.mark.parametrize(
    "input_",
    [
        Path(mm_path) / "MMConfig_demo.cfg",  # type: ignore
        Path(__file__).parent / "local_config.cfg",
    ],
)
def test_model_load_and_save(tmp_path: Path, input_: Path):
    output = tmp_path / "MMConfig_demo.cfg"
    scope = Microscope()
    scope.load_config(input_)
    scope.save(output)

    assert output.exists()

    # for now we only assert that the non-empty lines are the same
    # we don't assert order
    assert set(non_empty_lines(input_)) == set(non_empty_lines(output))


def _assert_cfg_matches_core_save(
    core: CMMCorePlus, model: Microscope, tmp_path: Path
) -> None:
    model_out = tmp_path / "model_out.cfg"
    core_out = tmp_path / "core_out.cfg"

    model.save(model_out)
    core.saveSystemConfiguration(str(core_out))

    # MMCore DOES write out default affine transforms... MMStudio doesn't and we don't
    core_lines = [
        x for x in non_empty_lines(core_out) if "1.0,0.0,0.0,0.0,1.0,0.0" not in x
    ]
    # MMCore doesn't write out AutoShutter prefs
    model_lines = [
        x
        for x in non_empty_lines(model_out)
        if not x.startswith("Property,Core,AutoShutter")
    ]
    assert core_lines == model_lines


def test_model_save_like_core1(tmp_path: Path) -> None:
    core = CMMCorePlus()
    core.loadSystemConfiguration()
    scope = Microscope.create_from_core(core)
    _assert_cfg_matches_core_save(core, scope, tmp_path)


def test_model_save_like_core2(tmp_path: Path) -> None:
    core = CMMCorePlus()
    scope = Microscope.create_from_core(core)
    _assert_cfg_matches_core_save(core, scope, tmp_path)


def test_model_save_like_core3(tmp_path: Path) -> None:
    core = CMMCorePlus()
    # empty configs
    core.defineConfigGroup("TestGroup")
    core.definePixelSizeConfig("PixConf")
    scope = Microscope.create_from_core(core)
    _assert_cfg_matches_core_save(core, scope, tmp_path)


def test_load_errors() -> None:
    model = Microscope()

    with pytest.raises(ValueError, match="Invalid command name"):
        model.load_config("NotACommand,1,2,3,4")
    with pytest.raises(ValueError, match="Expected 3 or 4 arguments, got 6"):
        model.load_config("Property,A,B,C,D,E")
    with pytest.raises(ValueError, match="not an integer"):
        model.load_config("Property,Core,Initialize,NotAnInt")
    with pytest.raises(ValueError, match="not an integer"):
        model.load_config(
            """
            Device,Dichroic,DemoCamera,DWheel
            Label,Dichroic,NotAnInt,Q505LP
            """
        )
    with pytest.raises(ValueError, match="'NotAPreset' not found"):
        model.load_config("PixelSize_um,NotAPreset,0.5")
    with pytest.raises(ValueError, match="Expected a float"):
        model.load_config(
            """
            ConfigPixelSize,Res40x,Objective,Label,Nikon 40X Plan Flueor ELWD
            PixelSize_um,Res40x,NotAFloat
            """
        )
    with pytest.raises(ValueError, match="'Res10x' not found"):
        model.load_config("PixelSizeAffine,Res10x,1.0,0.0,0.0,0.0,1.1,0.0")
    with pytest.raises(ValueError, match="Expected 8 arguments, got 5"):
        model.load_config(
            """
            ConfigPixelSize,Res40x,Objective,Label,Nikon 40X Plan Flueor ELWD
            PixelSizeAffine,Res40x,1.0,0.0,0.0
            """
        )
    with pytest.raises(ValueError, match="Expected 6 floats"):
        model.load_config(
            """
            ConfigPixelSize,Res40x,Objective,Label,Nikon 40X Plan Flueor ELWD
            PixelSizeAffine,Res40x,1.0,0.0,0.0,0.0,1.1,NoFloat
            """
        )
    with pytest.raises(ValueError, match="Expected a float"):
        model.load_config(
            """
            Device,Shutter,DemoCamera,DShutter
            Delay,Shutter,NotAFloat
            """
        )
    with pytest.raises(ValueError, match="not a valid FocusDirection"):
        model.load_config(
            """
            Device,Z,DemoCamera,DStage
            FocusDirection,Z,9
            """
        )

    # for now
    with pytest.warns(RuntimeWarning, match="not implemented"):
        model.load_config("Equipment,1,2,3,4")


def test_scope_errs():
    with pytest.raises(ValueError, match="Cannot create a Device with type Core"):
        Device(name="Core", device_type=DeviceType.Core)
    with pytest.raises(ValueError, match="Cannot have CoreDevice in devices list"):
        Microscope(devices=[CoreDevice()])


def test_apply():
    core1 = CMMCorePlus()
    core1.loadSystemConfiguration()
    state1 = core1.getSystemState()
    model = Microscope.create_from_core(core1)
    assert model.get_device("LED Shutter").get_property("State Device").value == "LED"
    assert core1.getProperty("Core", "XYStage") == "XY"

    core2 = CMMCorePlus()
    model.apply_to_core(core2)
    state2 = core2.getSystemState()
    assert core2.getProperty("LED Shutter", "State Device") == "LED"
    assert core2.getProperty("Core", "XYStage") == "XY"
    assert list(state1) == list(state2)

    core3 = CMMCorePlus()
    model.initialize(core3)
    assert core3.getProperty("Camera", "Binning") == "1"


def test_rich_repr():
    pytest.importorskip("rich")
    from rich import pretty

    core = CMMCorePlus()
    core.loadSystemConfiguration()
    scope = Microscope.create_from_core(core)

    pretty.pretty_repr(scope)


def test_dirty():
    scope = Microscope()
    assert not scope.is_dirty()
    scope.devices.append(Device("name"))
    assert scope.is_dirty()
    scope.mark_clean()
    assert not scope.is_dirty()
