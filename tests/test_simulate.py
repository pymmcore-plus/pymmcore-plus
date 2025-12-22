"""Tests for the experimental simulate module."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import numpy as np
import pytest

import pymmcore_plus.experimental.simulate as sim
from pymmcore_plus.experimental.simulate._render import RenderEngine

if TYPE_CHECKING:
    import pymmcore_plus
    from pymmcore_plus.experimental.simulate._render import Backend
    from pymmcore_plus.metadata.schema import SummaryMetaV1

HAS_CV2 = importlib.util.find_spec("cv2")

# =============================================================================
# Test utilities and fixtures
# =============================================================================


@pytest.fixture
def mock_state() -> SummaryMetaV1:
    """Create a mock SummaryMetaV1 state.

    Camera parameters are set to produce reasonable signal levels:
    - 100ms exposure, gain=0, 8-bit, FWC=255 (maps 1:1 to ADU at unity gain)
    - photon_flux=1000 default, QE=0.8 default
    - With intensity=200: ~628 photons → ~502 electrons → ~200 ADU
    """
    return {
        "format": "summary-dict",
        "version": "1.0",
        "image_infos": (
            {
                "camera_label": "Camera",
                "width": 512,
                "height": 512,
                "pixel_size_um": 1.0,
                "plane_shape": (512, 512),
                "dtype": "uint8",
                "pixel_format": "Mono8",
                "pixel_size_config_name": "Res10x",
            },
        ),
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "devices": (
            {
                "label": "Camera",
                "type": "Camera",
                "library": "DemoCamera",
                "name": "DCam",
                "description": "Demo camera",
                "properties": (
                    {
                        "name": "Exposure",
                        "value": "100.0",
                        "data_type": "float",
                        "is_read_only": False,
                    },
                    {
                        "name": "Offset",
                        "value": "0",
                        "data_type": "int",
                        "is_read_only": False,
                    },
                    {
                        "name": "Gain",
                        "value": "0",
                        "data_type": "int",
                        "is_read_only": False,
                    },
                    {
                        "name": "BitDepth",
                        "value": "8",
                        "data_type": "int",
                        "is_read_only": False,
                    },
                    {
                        "name": "ReadNoise (electrons)",
                        "value": "0",
                        "data_type": "float",
                        "is_read_only": False,
                    },
                    # Set FWC low for 8-bit to get reasonable signal levels
                    # At unity gain (0), FWC electrons = max gray value (255)
                    {
                        "name": "Full Well Capacity",
                        "value": "255",
                        "data_type": "float",
                        "is_read_only": True,
                    },
                    {
                        "name": "Photon Flux",
                        "value": "1000",
                        "data_type": "float",
                        "is_read_only": False,
                    },
                    {
                        "name": "Quantum Efficiency",
                        "value": "0.8",
                        "data_type": "float",
                        "is_read_only": True,
                    },
                ),
            },
            {
                "label": "Core",
                "library": "",
                "name": "Core",
                "type": "CoreDevice",
                "description": "Core device",
                "properties": (
                    {
                        "name": "Camera",
                        "value": "Camera",
                        "data_type": "str",
                        "allowed_values": ("", "Camera"),
                        "is_read_only": False,
                    },
                    {
                        "name": "Focus",
                        "value": "Z",
                        "data_type": "str",
                        "allowed_values": ("", "Z"),
                        "is_read_only": False,
                    },
                    {
                        "name": "XYStage",
                        "value": "XY",
                        "data_type": "str",
                        "allowed_values": ("", "XY"),
                        "is_read_only": False,
                    },
                ),
            },
        ),
        "system_info": {
            "pymmcore_version": "X.Y.Z",
            "pymmcore_plus_version": "X.Y.Z",
            "mmcore_version": "X.Y.Z",
            "device_api_version": "X.Y.Z",
            "device_adapter_search_paths": ("",),
            "system_configuration_file": None,
            "primary_log_file": "log.txt",
            "sequence_buffer_size_mb": 500,
            "continuous_focus_enabled": True,
            "continuous_focus_locked": True,
            "auto_shutter": True,
        },
        "config_groups": (),
        "pixel_size_configs": (),
    }


# =============================================================================
# Test rects_intersect
# =============================================================================


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((0, 0, 10, 10), (5, 5, 15, 15), True),  # Overlapping
        ((0, 0, 10, 10), (10, 0, 20, 10), True),  # Touching edges
        ((0, 0, 10, 10), (20, 20, 30, 30), False),  # Non-overlapping
        ((0, 0, 10, 10), (11, 0, 20, 10), False),  # Gap between
        ((0, 0, 100, 100), (10, 10, 20, 20), True),  # One inside other
        ((0, 0, 10, 10), (0, 0, 10, 10), True),  # Same rectangle
    ],
)
def test_rects_intersect(a: tuple, b: tuple, expected: bool) -> None:
    assert sim.rects_intersect(a, b) is expected


# =============================================================================
# Test SampleObject classes
# =============================================================================


@pytest.mark.parametrize(
    ("obj", "expected_bounds"),
    [
        (sim.Point(10.0, 20.0, radius=5.0), (5.0, 15.0, 15.0, 25.0)),
        (sim.Line((10.0, 20.0), (50.0, 30.0)), (10.0, 20.0, 50.0, 30.0)),
        (sim.Line((50.0, 30.0), (10.0, 20.0)), (10.0, 20.0, 50.0, 30.0)),  # Reversed
        (sim.Rectangle((10.0, 20.0), 30.0, 40.0), (10.0, 20.0, 40.0, 60.0)),
        (sim.Ellipse((50.0, 50.0), 20.0, 10.0), (30.0, 40.0, 70.0, 60.0)),
        (
            sim.Polygon([(5.0, 10.0), (15.0, 5.0), (20.0, 15.0), (10.0, 20.0)]),
            (5.0, 5.0, 20.0, 20.0),
        ),
        (
            sim.RegularPolygon((50.0, 50.0), radius=20.0, n_sides=6),
            (30.0, 30.0, 70.0, 70.0),
        ),
        (
            sim.Arc((50.0, 50.0), rx=20.0, ry=10.0, start_angle=0, end_angle=180),
            (30.0, 40.0, 70.0, 60.0),
        ),
    ],
)
def test_object_bounds(obj: object, expected_bounds: tuple) -> None:
    assert obj.get_bounds() == expected_bounds


def test_point_defaults() -> None:
    p = sim.Point(10.0, 20.0)
    assert (p.x, p.y, p.intensity, p.radius) == (10.0, 20.0, 255, 2.0)


def test_point_should_draw() -> None:
    p = sim.Point(10.0, 10.0, radius=2.0)
    assert p.should_draw((0, 0, 100, 100)) is True  # Inside
    assert p.should_draw((50, 50, 100, 100)) is False  # Outside
    assert p.should_draw((8, 8, 20, 20)) is True  # Partial


def test_line_defaults() -> None:
    line = sim.Line((0.0, 0.0), (100.0, 100.0))
    assert (line.start, line.end, line.intensity, line.width) == (
        (0.0, 0.0),
        (100.0, 100.0),
        255,
        1,
    )


def test_rectangle_bottom_right() -> None:
    rect = sim.Rectangle((10.0, 20.0), 30.0, 40.0)
    assert rect.bottom_right == (40.0, 60.0)
    assert rect.fill is False


def test_regular_polygon_vertices() -> None:
    poly = sim.RegularPolygon((50.0, 50.0), radius=20.0, n_sides=6)
    assert len(poly._vertices) == 6


def test_bitmap_from_array() -> None:
    arr = np.random.randint(0, 255, (50, 100), dtype=np.uint8)
    bitmap = sim.Bitmap((10.0, 20.0), arr)
    assert bitmap.top_left == (10.0, 20.0)
    assert bitmap._image.size == (100, 50)  # PIL uses (width, height)


def test_bitmap_bounds_with_scale() -> None:
    arr = np.zeros((50, 100), dtype=np.uint8)
    bitmap = sim.Bitmap((10.0, 20.0), arr, bitmap_scale=2.0)
    assert bitmap.get_bounds() == (10.0, 20.0, 210.0, 120.0)


def test_bitmap_invalid_type() -> None:
    with pytest.raises(TypeError, match="Invalid bitmap type"):
        sim.Bitmap((0, 0), [1, 2, 3])


# =============================================================================
# Test RenderConfig
# =============================================================================


def test_render_config_defaults() -> None:
    config = sim.RenderConfig()
    assert config.shot_noise is True
    assert config.defocus_scale == 0.125
    assert config.base_blur == 1.5
    assert config.random_seed is None
    assert config.backend == "auto"


def test_render_config_custom() -> None:
    config = sim.RenderConfig(
        shot_noise=False, defocus_scale=0.2, random_seed=42, backend="pil"
    )
    assert config.shot_noise is False
    assert config.defocus_scale == 0.2
    assert config.random_seed == 42
    assert config.backend == "pil"


# =============================================================================
# Test RenderEngine
# =============================================================================


def test_engine_creation() -> None:
    engine = RenderEngine([sim.Point(0, 0)])
    assert len(engine.objects) == 1
    assert isinstance(engine.config, sim.RenderConfig)


def test_render_empty_sample(mock_state: SummaryMetaV1) -> None:
    img = RenderEngine([]).render(mock_state)
    assert img.shape == (512, 512)
    assert img.dtype == np.uint8


def test_render_single_point(mock_state: SummaryMetaV1) -> None:
    config = sim.RenderConfig(shot_noise=False, base_blur=0)
    img = RenderEngine([sim.Point(0, 0, intensity=200, radius=10)], config).render(
        mock_state
    )
    assert img.shape == (512, 512)
    assert img[256, 256] > 0  # Center should have intensity


def test_render_with_offset(mock_state: SummaryMetaV1) -> None:
    config = sim.RenderConfig(shot_noise=False, base_blur=0)
    engine = RenderEngine([sim.Point(100, 100, intensity=200, radius=10)], config)

    img1 = engine.render(mock_state)
    mock_state["position"]["x"] = 100.0
    mock_state["position"]["y"] = 100.0
    img2 = engine.render(mock_state)

    assert img2[256, 256] > img1[256, 256]  # Point now at center


def test_render_16bit(mock_state: SummaryMetaV1) -> None:
    # Set camera to 16-bit
    for dev in mock_state["devices"]:
        if dev["label"] == "Camera":
            for prop in dev["properties"]:
                if prop["name"] == "BitDepth":
                    prop["value"] = "16"
    config = sim.RenderConfig(shot_noise=False)
    img = RenderEngine([sim.Point(0, 0, intensity=200)], config).render(mock_state)
    assert img.dtype == np.uint16


def test_render_with_defocus(mock_state: SummaryMetaV1) -> None:
    # Use lower intensity to avoid saturation which breaks ratio comparison
    config = sim.RenderConfig(shot_noise=False, base_blur=0, defocus_scale=1.0)
    engine = RenderEngine([sim.Point(0, 0, intensity=50, radius=1)], config)

    mock_state["position"]["z"] = 0.0
    img_focus = engine.render(mock_state)

    mock_state["position"]["z"] = 10.0
    img_defocus = engine.render(mock_state)

    # Focused should have higher concentration in center
    h, w = img_focus.shape
    center_focus = img_focus[h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5].sum()
    center_defocus = img_defocus[h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5].sum()
    total_focus, total_defocus = img_focus.sum(), img_defocus.sum()

    if total_focus > 0 and total_defocus > 0:
        assert center_focus / total_focus > center_defocus / total_defocus


def test_render_reproducible_with_seed(mock_state: SummaryMetaV1) -> None:
    # Test that random seed produces reproducible results with shot noise
    config = sim.RenderConfig(random_seed=42, shot_noise=True)
    img1 = RenderEngine([sim.Point(0, 0, intensity=100)], config).render(mock_state)
    img2 = RenderEngine(
        [sim.Point(0, 0, intensity=100)],
        sim.RenderConfig(random_seed=42, shot_noise=True),
    ).render(mock_state)
    np.testing.assert_array_equal(img1, img2)


# =============================================================================
# Test Sample integration
# =============================================================================


def test_sample_creation() -> None:
    sample = sim.Sample([sim.Point(0, 0), sim.Line((0, 0), (10, 10))])
    assert len(sample.objects) == 2


def test_sample_patch_context_manager(core: pymmcore_plus.CMMCorePlus) -> None:
    sample = sim.Sample([sim.Point(0, 0, intensity=200)])
    with sample.patch(core):
        core.snapImage()
        assert isinstance(core.getImage(), np.ndarray)


def test_sample_render_with_state(core: pymmcore_plus.CMMCorePlus) -> None:
    sample = sim.Sample([sim.Point(0, 0, intensity=200)])
    assert isinstance(sample.render(core.state()), np.ndarray)


def test_sample_repr() -> None:
    repr_str = repr(sim.Sample([sim.Point(0, 0), sim.Point(1, 1)]))
    assert "2 objects" in repr_str


def test_sample_integration_stage_movement(core: pymmcore_plus.CMMCorePlus) -> None:
    config = sim.RenderConfig(shot_noise=False, base_blur=0)
    sample = sim.Sample([sim.Point(0, 0, intensity=255, radius=10)], config)

    with sample.patch(core):
        # Ensure stage is at origin so point at (0,0) should be at image center
        core.setXYPosition(0, 0)
        core.snapImage()
        img = core.getImage()
        assert img.sum() > 0

        h, w = img.shape
        max_y, max_x = np.unravel_index(img.argmax(), img.shape)
        # Allow 10% tolerance - exact position varies due to rounding and backends
        assert abs(max_x - w // 2) < w * 0.1
        assert abs(max_y - h // 2) < h * 0.1


def test_sample_integration_z_defocus(core: pymmcore_plus.CMMCorePlus) -> None:
    config = sim.RenderConfig(shot_noise=False, base_blur=0, defocus_scale=0.5)
    sample = sim.Sample([sim.Point(0, 0, intensity=255, radius=3)], config)

    with sample.patch(core):
        core.setXYPosition(0, 0)

        core.setZPosition(0)
        core.snapImage()
        img_focus = core.getImage()

        core.setZPosition(20)
        core.snapImage()
        img_defocus = core.getImage()

        h, w = img_focus.shape
        center_focus = img_focus[h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5].sum()
        center_defocus = img_defocus[
            h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5
        ].sum()
        total_focus, total_defocus = float(img_focus.sum()), float(img_defocus.sum())

        if total_focus > 0 and total_defocus > 0:
            assert center_focus / total_focus > center_defocus / total_defocus


# =============================================================================
# Test both PIL and cv2 rendering backends
# =============================================================================


@pytest.fixture
def all_object_types() -> list:
    """Create one of each object type for testing."""
    return [
        sim.Point(0, 0, intensity=100, radius=5),
        sim.Line((0, 0), (10, 10), intensity=100),
        sim.Rectangle((0, 0), 10, 10, intensity=100, fill=True),
        sim.Ellipse((0, 0), 5, 3, intensity=100, fill=True),
        sim.Polygon([(0, 0), (10, 0), (5, 10)], intensity=100, fill=True),
        sim.RegularPolygon((0, 0), radius=5, n_sides=6, intensity=100, fill=True),
        sim.Arc((0, 0), 5, 5, 0, 180, intensity=100),
    ]


@pytest.mark.parametrize("backend", ["pil", "cv2"])
def test_render_backend(
    mock_state: SummaryMetaV1, all_object_types: list, backend: Backend
) -> None:
    """Test that both backends produce valid output."""
    if backend == "cv2" and not HAS_CV2:
        pytest.skip("opencv-python not installed")

    config = sim.RenderConfig(shot_noise=False, base_blur=0, backend=backend)
    engine = RenderEngine(all_object_types, config)
    img = engine.render(mock_state)

    assert img.shape == (512, 512)
    assert img.dtype == np.uint8
    assert img.sum() > 0


@pytest.mark.parametrize("backend", ["pil", "cv2"])
def test_render_blur_backend(mock_state: SummaryMetaV1, backend: Backend) -> None:
    """Test that blur works with both backends."""
    if backend == "cv2" and not HAS_CV2:
        pytest.skip("opencv-python not installed")

    config = sim.RenderConfig(shot_noise=False, base_blur=2.0, backend=backend)
    engine = RenderEngine([sim.Point(0, 0, intensity=255, radius=3)], config)
    img = engine.render(mock_state)
    assert img.sum() > 0


@pytest.mark.skipif(not HAS_CV2, reason="opencv-python not installed")
def test_draw_cv2_methods() -> None:
    """Test draw_cv2 methods on individual objects (requires cv2)."""

    def transform(x: float, y: float) -> tuple[int, int]:
        return int(x) + 50, int(y) + 50

    objects = [
        sim.Point(0, 0, intensity=100, radius=5),
        sim.Line((-10, -10), (10, 10), intensity=100),
        sim.Rectangle((-5, -5), 10, 10, intensity=100, fill=True),
        sim.Ellipse((0, 0), 8, 5, intensity=100, fill=True),
        sim.Polygon([(-5, -5), (5, -5), (0, 5)], intensity=100, fill=True),
        sim.Arc((0, 0), 10, 10, 0, 90, intensity=100),
    ]

    img = np.zeros((100, 100), dtype=np.uint8)
    for obj in objects:
        obj.draw_cv2(img, transform, scale=1.0)

    assert img.sum() > 0


@pytest.mark.skipif(not HAS_CV2, reason="opencv-python not installed")
def test_backend_consistency(mock_state: sim.SummaryMetaV1) -> None:
    """Test PIL and CV2 backends produce similar results.

    Small differences are expected due to rasterization algorithms:
    - PIL draws rounder circles at small radii
    - CV2 circles are more diamond-shaped at small radii
    These differences become negligible with blur applied.
    """
    from pymmcore_plus.experimental.simulate._render import RenderEngine

    # Test objects with various shapes
    test_cases = [
        ("Line", [sim.Line((-50, -50), (50, 50), intensity=200)], 0.05),
        (
            "Rectangle",
            [sim.Rectangle((-30, -20), 60, 40, intensity=200, fill=True)],
            0.05,
        ),
        ("Ellipse", [sim.Ellipse((0, 0), 30, 20, intensity=200, fill=True)], 0.05),
        ("Point (large)", [sim.Point(0, 0, intensity=200, radius=10)], 0.15),
        # Small points have larger differences due to rasterization
        ("Point (small)", [sim.Point(0, 0, intensity=200, radius=3)], 0.40),
    ]

    for name, objects, tolerance in test_cases:
        config_pil = sim.RenderConfig(shot_noise=False, base_blur=0, backend="pil")
        config_cv2 = sim.RenderConfig(shot_noise=False, base_blur=0, backend="cv2")

        img_pil = RenderEngine(objects, config_pil).render(mock_state)
        img_cv2 = RenderEngine(objects, config_cv2).render(mock_state)

        pil_sum = float(img_pil.sum())
        cv2_sum = float(img_cv2.sum())
        diff_pct = (
            abs(pil_sum - cv2_sum) / max(pil_sum, cv2_sum)
            if max(pil_sum, cv2_sum) > 0
            else 0
        )

        assert diff_pct < tolerance, (
            f"{name}: {diff_pct:.1%} diff exceeds {tolerance:.0%} tolerance"
        )
