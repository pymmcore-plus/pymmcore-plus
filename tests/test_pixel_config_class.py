from pymmcore_plus import CMMCorePlus
from pymmcore_plus.model import PixelSizeGroup, PixelSizePreset, Setting


def test_pixel_config_class():
    core = CMMCorePlus()
    core.loadSystemConfiguration()

    new_px_group = PixelSizeGroup(
        presets={
            "test": PixelSizePreset(
                name="test",
                settings=[Setting("Core", "Camera", "Camera")],
                pixel_size_um=0.1,
                affine=(1, 0, 0, 0, 1, 0),
            )
        }
    )
    new_px_group.apply_to_core(core)
    assert len(core.getAvailablePixelSizeConfigs()) == 4
    assert "test" in core.getAvailablePixelSizeConfigs()
    assert core.getPixelSizeUmByID("test") == 0.1
    assert tuple(core.getPixelSizeAffineByID("test")) == (1, 0, 0, 0, 1, 0)
