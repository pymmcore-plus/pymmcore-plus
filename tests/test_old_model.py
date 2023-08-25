from __future__ import annotations

import os
from pathlib import Path

import pytest
from pymmcore_plus import CMMCorePlus, find_micromanager
from pymmcore_plus._old_model import Microscope


def test_model_create() -> None:
    model = Microscope()
    assert model.devices
    assert list(model.devices[0].setup_props())

    with pytest.raises(ValueError):
        model.find_device("NotADevice")


def test_model_from_core(core: CMMCorePlus) -> None:
    model = Microscope(from_core=core)
    assert model.devices
    assert model.hub_devices
    if os.name == "nt":
        assert model.bad_libraries

    model2 = Microscope()
    model2.update_from_core(core)

    assert model == model2


@pytest.mark.parametrize(
    "input_",
    [
        Path(find_micromanager()) / "MMConfig_demo.cfg",  # type: ignore
        Path(__file__).parent / "local_config.cfg",
    ],
)
def test_model_load_and_save(tmp_path: Path, input_: Path):
    output = tmp_path / "MMConfig_demo.cfg"
    scope = Microscope()
    scope.load(input_)
    scope.save(output)

    assert output.exists()

    # for now we only assert that the non-empty lines are the same
    # we don't assert order
    def non_empty_lines(path: Path) -> set[str]:
        return {
            ln
            for line in path.read_text().splitlines()
            if (ln := line.strip()) and not ln.startswith("#")
        }

    assert non_empty_lines(input_) == non_empty_lines(output)


def test_load_errors() -> None:
    model = Microscope()

    with pytest.raises(ValueError, match="Invalid command name"):
        model.load_from_string("NotACommand,1,2,3,4")
    with pytest.raises(ValueError, match="Expected 3 or 4 arguments, got 6"):
        model.load_from_string("Property,A,B,C,D,E")
    with pytest.raises(ValueError, match="not an integer"):
        model.load_from_string("Property,Core,Initialize,NotAnInt")
    with pytest.raises(ValueError, match="not an integer"):
        model.load_from_string(
            """
            Device,Dichroic,DemoCamera,DWheel
            Label,Dichroic,NotAnInt,Q505LP
            """
        )
    with pytest.raises(ValueError, match="'NotAPreset' not found"):
        model.load_from_string("PixelSize_um,NotAPreset,0.5")
    with pytest.raises(ValueError, match="Expected a float"):
        model.load_from_string(
            """
            ConfigPixelSize,Res40x,Objective,Label,Nikon 40X Plan Flueor ELWD
            PixelSize_um,Res40x,NotAFloat
            """
        )
    with pytest.raises(ValueError, match="'Res10x' not found"):
        model.load_from_string("PixelSizeAffine,Res10x,1.0,0.0,0.0,0.0,1.1,0.0")
    with pytest.raises(ValueError, match="Expected 8 arguments, got 5"):
        model.load_from_string(
            """
            ConfigPixelSize,Res40x,Objective,Label,Nikon 40X Plan Flueor ELWD
            PixelSizeAffine,Res40x,1.0,0.0,0.0
            """
        )
    with pytest.raises(ValueError, match="Expected 6 floats"):
        model.load_from_string(
            """
            ConfigPixelSize,Res40x,Objective,Label,Nikon 40X Plan Flueor ELWD
            PixelSizeAffine,Res40x,1.0,0.0,0.0,0.0,1.1,NoFloat
            """
        )
    with pytest.raises(ValueError, match="Expected a float"):
        model.load_from_string(
            """
            Device,Shutter,DemoCamera,DShutter
            Delay,Shutter,NotAFloat
            """
        )
    with pytest.raises(ValueError, match="not a valid FocusDirection"):
        model.load_from_string(
            """
            Device,Z,DemoCamera,DStage
            FocusDirection,Z,9
            """
        )

    # for now
    with pytest.warns(RuntimeWarning, match="not implemented"):
        model.load_from_string("Equipment,1,2,3,4")
