"""Tests for the experimental simulate module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from pymmcore_plus.experimental.simulate import (
    Arc,
    Bitmap,
    Ellipse,
    Line,
    Point,
    Polygon,
    Rectangle,
    RegularPolygon,
    RenderConfig,
    RenderEngine,
    Sample,
    rects_intersect,
)

if TYPE_CHECKING:
    import pymmcore_plus


# =============================================================================
# Test utilities
# =============================================================================


def test_rects_intersect() -> None:
    """Test rectangle intersection detection."""
    # Overlapping rectangles
    assert rects_intersect((0, 0, 10, 10), (5, 5, 15, 15)) is True
    # Touching rectangles (edges touching counts as intersection)
    assert rects_intersect((0, 0, 10, 10), (10, 0, 20, 10)) is True
    # Non-overlapping rectangles
    assert rects_intersect((0, 0, 10, 10), (20, 20, 30, 30)) is False
    # Gap between rectangles
    assert rects_intersect((0, 0, 10, 10), (11, 0, 20, 10)) is False
    # One inside the other
    assert rects_intersect((0, 0, 100, 100), (10, 10, 20, 20)) is True
    # Same rectangle
    assert rects_intersect((0, 0, 10, 10), (0, 0, 10, 10)) is True


# =============================================================================
# Test SampleObject classes
# =============================================================================


class TestPoint:
    """Tests for Point sample object."""

    def test_point_creation(self) -> None:
        """Test Point creation with defaults."""
        p = Point(10.0, 20.0)
        assert p.x == 10.0
        assert p.y == 20.0
        assert p.intensity == 255
        assert p.radius == 2.0

    def test_point_custom_params(self) -> None:
        """Test Point creation with custom parameters."""
        p = Point(5.0, 15.0, intensity=128, radius=5.0)
        assert p.x == 5.0
        assert p.y == 15.0
        assert p.intensity == 128
        assert p.radius == 5.0

    def test_point_bounds(self) -> None:
        """Test Point bounding box calculation."""
        p = Point(10.0, 20.0, radius=5.0)
        bounds = p.get_bounds()
        assert bounds == (5.0, 15.0, 15.0, 25.0)

    def test_point_should_draw(self) -> None:
        """Test Point FOV intersection check."""
        p = Point(10.0, 10.0, radius=2.0)
        # Inside FOV
        assert p.should_draw((0, 0, 100, 100)) is True
        # Outside FOV
        assert p.should_draw((50, 50, 100, 100)) is False
        # Partially inside
        assert p.should_draw((8, 8, 20, 20)) is True


class TestLine:
    """Tests for Line sample object."""

    def test_line_creation(self) -> None:
        """Test Line creation."""
        line = Line((0.0, 0.0), (100.0, 100.0))
        assert line.start == (0.0, 0.0)
        assert line.end == (100.0, 100.0)
        assert line.intensity == 255
        assert line.width == 1

    def test_line_bounds(self) -> None:
        """Test Line bounding box calculation."""
        line = Line((10.0, 20.0), (50.0, 30.0))
        bounds = line.get_bounds()
        assert bounds == (10.0, 20.0, 50.0, 30.0)

        # Reversed direction
        line2 = Line((50.0, 30.0), (10.0, 20.0))
        bounds2 = line2.get_bounds()
        assert bounds2 == (10.0, 20.0, 50.0, 30.0)


class TestRectangle:
    """Tests for Rectangle sample object."""

    def test_rectangle_creation(self) -> None:
        """Test Rectangle creation."""
        rect = Rectangle((10.0, 20.0), 30.0, 40.0)
        assert rect.top_left == (10.0, 20.0)
        assert rect.width == 30.0
        assert rect.height == 40.0
        assert rect.fill is False

    def test_rectangle_bounds(self) -> None:
        """Test Rectangle bounding box calculation."""
        rect = Rectangle((10.0, 20.0), 30.0, 40.0)
        bounds = rect.get_bounds()
        assert bounds == (10.0, 20.0, 40.0, 60.0)

    def test_rectangle_bottom_right(self) -> None:
        """Test Rectangle bottom_right property."""
        rect = Rectangle((10.0, 20.0), 30.0, 40.0)
        assert rect.bottom_right == (40.0, 60.0)


class TestEllipse:
    """Tests for Ellipse sample object."""

    def test_ellipse_creation(self) -> None:
        """Test Ellipse creation."""
        ellipse = Ellipse((50.0, 50.0), 20.0, 10.0)
        assert ellipse.center == (50.0, 50.0)
        assert ellipse.rx == 20.0
        assert ellipse.ry == 10.0

    def test_ellipse_bounds(self) -> None:
        """Test Ellipse bounding box calculation."""
        ellipse = Ellipse((50.0, 50.0), 20.0, 10.0)
        bounds = ellipse.get_bounds()
        assert bounds == (30.0, 40.0, 70.0, 60.0)


class TestPolygon:
    """Tests for Polygon sample object."""

    def test_polygon_creation(self) -> None:
        """Test Polygon creation."""
        vertices = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        poly = Polygon(vertices)
        assert poly.vertices == vertices

    def test_polygon_bounds(self) -> None:
        """Test Polygon bounding box calculation."""
        vertices = [(5.0, 10.0), (15.0, 5.0), (20.0, 15.0), (10.0, 20.0)]
        poly = Polygon(vertices)
        bounds = poly.get_bounds()
        assert bounds == (5.0, 5.0, 20.0, 20.0)


class TestRegularPolygon:
    """Tests for RegularPolygon sample object."""

    def test_regular_polygon_creation(self) -> None:
        """Test RegularPolygon creation."""
        poly = RegularPolygon((50.0, 50.0), radius=20.0, n_sides=6)
        assert poly.center == (50.0, 50.0)
        assert poly.radius == 20.0
        assert poly.n_sides == 6
        assert len(poly._vertices) == 6

    def test_regular_polygon_bounds(self) -> None:
        """Test RegularPolygon bounding box calculation."""
        poly = RegularPolygon((50.0, 50.0), radius=20.0, n_sides=6)
        bounds = poly.get_bounds()
        assert bounds == (30.0, 30.0, 70.0, 70.0)


class TestArc:
    """Tests for Arc sample object."""

    def test_arc_creation(self) -> None:
        """Test Arc creation."""
        arc = Arc((50.0, 50.0), rx=20.0, ry=10.0, start_angle=0, end_angle=180)
        assert arc.center == (50.0, 50.0)
        assert arc.start_angle == 0
        assert arc.end_angle == 180


class TestBitmap:
    """Tests for Bitmap sample object."""

    def test_bitmap_from_array(self) -> None:
        """Test Bitmap creation from numpy array."""
        arr = np.random.randint(0, 255, (50, 100), dtype=np.uint8)
        bitmap = Bitmap((10.0, 20.0), arr)
        assert bitmap.top_left == (10.0, 20.0)
        assert bitmap._image.size == (100, 50)  # PIL uses (width, height)

    def test_bitmap_bounds(self) -> None:
        """Test Bitmap bounding box calculation."""
        arr = np.zeros((50, 100), dtype=np.uint8)
        bitmap = Bitmap((10.0, 20.0), arr, bitmap_scale=2.0)
        bounds = bitmap.get_bounds()
        # width=100*2=200, height=50*2=100
        assert bounds == (10.0, 20.0, 210.0, 120.0)

    def test_bitmap_invalid_type(self) -> None:
        """Test Bitmap raises error for invalid input type."""
        with pytest.raises(TypeError, match="Invalid bitmap type"):
            Bitmap((0, 0), [1, 2, 3])  # type: ignore[arg-type]


# =============================================================================
# Test RenderConfig
# =============================================================================


class TestRenderConfig:
    """Tests for RenderConfig."""

    def test_default_config(self) -> None:
        """Test default RenderConfig values."""
        config = RenderConfig()
        assert config.noise_std == 3.0
        assert config.shot_noise is True
        assert config.defocus_scale == 0.125
        assert config.base_blur == 1.0
        assert config.intensity_scale == 1.0
        assert config.background == 0
        assert config.bit_depth == 8
        assert config.random_seed is None

    def test_custom_config(self) -> None:
        """Test custom RenderConfig values."""
        config = RenderConfig(
            noise_std=5.0,
            shot_noise=False,
            defocus_scale=0.2,
            bit_depth=16,
            random_seed=42,
        )
        assert config.noise_std == 5.0
        assert config.shot_noise is False
        assert config.defocus_scale == 0.2
        assert config.bit_depth == 16
        assert config.random_seed == 42


# =============================================================================
# Test RenderEngine
# =============================================================================


class TestRenderEngine:
    """Tests for RenderEngine."""

    @pytest.fixture
    def mock_state(self) -> dict:
        """Create a mock SummaryMetaV1 state."""
        return {
            "format": "summary-dict",
            "version": "1.0",
            "image_infos": [
                {
                    "camera_label": "Camera",
                    "width": 512,
                    "height": 512,
                    "pixel_size_um": 1.0,
                    "plane_shape": (512, 512),
                    "dtype": "uint8",
                    "pixel_format": "Mono8",
                    "pixel_size_config_name": "Res10x",
                }
            ],
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "devices": [
                {
                    "label": "Camera",
                    "type": "Camera",
                    "library": "DemoCamera",
                    "name": "DCam",
                    "description": "Demo camera",
                    "properties": [
                        {
                            "name": "Exposure",
                            "value": "100.0",
                            "data_type": "float",
                            "is_read_only": False,
                        }
                    ],
                }
            ],
            "system_info": {},
            "config_groups": (),
            "pixel_size_configs": (),
        }

    def test_engine_creation(self) -> None:
        """Test RenderEngine creation."""
        engine = RenderEngine([Point(0, 0)])
        assert len(engine.objects) == 1
        assert isinstance(engine.config, RenderConfig)

    def test_render_empty_sample(self, mock_state: dict) -> None:
        """Test rendering with no objects."""
        engine = RenderEngine([])
        img = engine.render(mock_state)  # type: ignore[arg-type]
        assert img.shape == (512, 512)
        assert img.dtype == np.uint8

    def test_render_single_point(self, mock_state: dict) -> None:
        """Test rendering a single point."""
        config = RenderConfig(noise_std=0, shot_noise=False, base_blur=0)
        engine = RenderEngine([Point(0, 0, intensity=200, radius=10)], config)
        img = engine.render(mock_state)  # type: ignore[arg-type]
        assert img.shape == (512, 512)
        # Center should have high intensity
        assert img[256, 256] > 0

    def test_render_with_offset(self, mock_state: dict) -> None:
        """Test rendering with stage offset."""
        config = RenderConfig(noise_std=0, shot_noise=False, base_blur=0)
        engine = RenderEngine([Point(100, 100, intensity=200, radius=10)], config)

        # Point at (100, 100), stage at (0, 0) -> point should be off-center
        img = engine.render(mock_state)  # type: ignore[arg-type]

        # Move stage to center on the point
        mock_state["position"]["x"] = 100.0
        mock_state["position"]["y"] = 100.0
        img2 = engine.render(mock_state)  # type: ignore[arg-type]

        # Point should now be at center
        assert img2[256, 256] > img[256, 256]

    def test_render_16bit(self, mock_state: dict) -> None:
        """Test 16-bit rendering."""
        config = RenderConfig(bit_depth=16, noise_std=0, shot_noise=False)
        engine = RenderEngine([Point(0, 0, intensity=200)], config)
        img = engine.render(mock_state)  # type: ignore[arg-type]
        assert img.dtype == np.uint16

    def test_render_with_defocus(self, mock_state: dict) -> None:
        """Test that defocus blur increases with Z."""
        config = RenderConfig(
            noise_std=0, shot_noise=False, base_blur=0, defocus_scale=1.0
        )
        engine = RenderEngine([Point(0, 0, intensity=255, radius=1)], config)

        # In focus (z=0)
        mock_state["position"]["z"] = 0.0
        img_focus = engine.render(mock_state)  # type: ignore[arg-type]

        # Out of focus (z=10)
        mock_state["position"]["z"] = 10.0
        img_defocus = engine.render(mock_state)  # type: ignore[arg-type]

        # Both images are normalized to 255, but defocused has more spread.
        # Check that center region has larger portion of total intensity when focused
        h, w = img_focus.shape
        center_region_focus = img_focus[
            h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5
        ].sum()
        center_region_defocus = img_defocus[
            h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5
        ].sum()
        total_focus = img_focus.sum()
        total_defocus = img_defocus.sum()

        # Focused should have higher concentration in center
        if total_focus > 0 and total_defocus > 0:
            focus_ratio = center_region_focus / total_focus
            defocus_ratio = center_region_defocus / total_defocus
            assert focus_ratio > defocus_ratio

    def test_render_reproducible_with_seed(self, mock_state: dict) -> None:
        """Test that random seed produces reproducible results."""
        config = RenderConfig(random_seed=42, noise_std=5.0)
        engine1 = RenderEngine([Point(0, 0, intensity=100)], config)
        img1 = engine1.render(mock_state)  # type: ignore[arg-type]

        config2 = RenderConfig(random_seed=42, noise_std=5.0)
        engine2 = RenderEngine([Point(0, 0, intensity=100)], config2)
        img2 = engine2.render(mock_state)  # type: ignore[arg-type]

        np.testing.assert_array_equal(img1, img2)


# =============================================================================
# Test Sample integration
# =============================================================================


class TestSample:
    """Tests for Sample class."""

    def test_sample_creation(self) -> None:
        """Test Sample creation."""
        objects = [Point(0, 0), Line((0, 0), (10, 10))]
        sample = Sample(objects)
        assert len(sample.objects) == 2
        assert sample.is_installed is False

    def test_sample_add_remove_objects(self) -> None:
        """Test adding and removing objects from sample."""
        sample = Sample([])
        assert len(sample.objects) == 0

        point = Point(0, 0)
        sample.add_object(point)
        assert len(sample.objects) == 1

        sample.remove_object(point)
        assert len(sample.objects) == 0

    def test_sample_clear_objects(self) -> None:
        """Test clearing all objects from sample."""
        sample = Sample([Point(0, 0), Point(1, 1), Point(2, 2)])
        assert len(sample.objects) == 3

        sample.clear_objects()
        assert len(sample.objects) == 0

    def test_sample_install_uninstall(self, core: pymmcore_plus.CMMCorePlus) -> None:
        """Test manual install/uninstall."""
        sample = Sample([Point(0, 0, intensity=200)])

        assert sample.is_installed is False
        sample.install(core)
        assert sample.is_installed is True

        # Should be able to snap and get image
        core.snapImage()
        img = core.getImage()
        assert isinstance(img, np.ndarray)

        sample.uninstall()
        assert sample.is_installed is False

    def test_sample_double_install_error(self, core: pymmcore_plus.CMMCorePlus) -> None:
        """Test that double install raises error."""
        sample = Sample([Point(0, 0)])
        sample.install(core)

        with pytest.raises(RuntimeError, match="already installed"):
            sample.install(core)

        sample.uninstall()

    def test_sample_uninstall_not_installed_error(self) -> None:
        """Test that uninstall when not installed raises error."""
        sample = Sample([Point(0, 0)])

        with pytest.raises(RuntimeError, match="not installed"):
            sample.uninstall()

    def test_sample_context_manager(self, core: pymmcore_plus.CMMCorePlus) -> None:
        """Test Sample as context manager."""
        sample = Sample([Point(0, 0, intensity=200)])

        with sample.patch(core):
            assert sample.is_installed is True
            core.snapImage()
            img = core.getImage()
            assert isinstance(img, np.ndarray)

        assert sample.is_installed is False

    def test_sample_context_manager_no_core_error(self) -> None:
        """Test that context manager without patch() raises error."""
        sample = Sample([Point(0, 0)])

        with pytest.raises(RuntimeError, match="No core set"):
            with sample:
                pass

    def test_sample_render_direct(self, core: pymmcore_plus.CMMCorePlus) -> None:
        """Test direct rendering without patching."""
        sample = Sample([Point(0, 0, intensity=200)])

        # With core set via patch()
        sample.patch(core)
        img = sample.render()
        assert isinstance(img, np.ndarray)

    def test_sample_render_with_state(self, core: pymmcore_plus.CMMCorePlus) -> None:
        """Test rendering with explicit state."""
        sample = Sample([Point(0, 0, intensity=200)])
        state = core.state()
        img = sample.render(state)
        assert isinstance(img, np.ndarray)

    def test_sample_repr(self) -> None:
        """Test Sample string representation."""
        sample = Sample([Point(0, 0), Point(1, 1)])
        repr_str = repr(sample)
        assert "2 objects" in repr_str
        assert "not installed" in repr_str

    def test_sample_integration_stage_movement(
        self, core: pymmcore_plus.CMMCorePlus
    ) -> None:
        """Test that stage position affects where objects appear in rendered image."""
        config = RenderConfig(noise_std=0, shot_noise=False, base_blur=0)

        # Create a point at the origin
        sample = Sample([Point(0, 0, intensity=255, radius=10)], config)

        with sample.patch(core):
            # Render with stage at origin - point should be at center
            core.snapImage()
            img1 = core.getImage()

            # Point should be visible and near center
            h, w = img1.shape
            assert img1.sum() > 0, "Image should have some intensity"

            # Find where the max is
            max_y, max_x = np.unravel_index(img1.argmax(), img1.shape)

            # Point at (0,0) with stage at (0,0) should appear near image center
            assert abs(max_x - w // 2) < 20, f"Point X near center, got {max_x}"
            assert abs(max_y - h // 2) < 20, f"Point Y near center, got {max_y}"

    def test_sample_integration_z_defocus(
        self, core: pymmcore_plus.CMMCorePlus
    ) -> None:
        """Test that Z position affects defocus blur."""
        config = RenderConfig(
            noise_std=0, shot_noise=False, base_blur=0, defocus_scale=0.5
        )
        sample = Sample([Point(0, 0, intensity=255, radius=3)], config)

        with sample.patch(core):
            core.setXYPosition(0, 0)

            # In focus
            core.setZPosition(0)
            core.snapImage()
            img_focus = core.getImage()

            # Out of focus
            core.setZPosition(20)
            core.snapImage()
            img_defocus = core.getImage()

            # Both are normalized to 255, check that blur spreads intensity
            # Focused should have more intensity concentrated in center
            h, w = img_focus.shape
            center_region_focus = img_focus[
                h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5
            ].sum()
            center_region_defocus = img_defocus[
                h // 2 - 5 : h // 2 + 5, w // 2 - 5 : w // 2 + 5
            ].sum()
            total_focus = float(img_focus.sum())
            total_defocus = float(img_defocus.sum())

            if total_focus > 0 and total_defocus > 0:
                focus_ratio = center_region_focus / total_focus
                defocus_ratio = center_region_defocus / total_defocus
                assert focus_ratio > defocus_ratio
