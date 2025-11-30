"""Rendering engine for simulated microscope samples.

Performance Notes
-----------------
The renderer uses several optimizations for speed:

1. **Intensity grouping** (~5x speedup): Objects are grouped by intensity value
   and drawn together on shared layers, reducing PIL Image allocations from
   O(n_objects) to O(n_unique_intensities).

2. **Optional OpenCV** (~25% speedup): When opencv-python is installed:
   - Drawing primitives use cv2 functions (~20% faster than PIL)
   - Gaussian blur uses cv2.GaussianBlur (~8x faster than PIL)
   Install with: `pip install opencv-python`

Typical performance (512x512, 630 objects):
- Without opencv-python: ~18ms
- With opencv-python: ~14ms
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

if TYPE_CHECKING:
    from typing_extensions import Literal, TypeAlias

    from pymmcore_plus.metadata.schema import ImageInfo, SummaryMetaV1

    from ._objects import Bounds, SampleObject, TransformFn

    Backend: TypeAlias = Literal["auto", "pil", "cv2"]

# OpenCV provides ~25% overall speedup when available:
# - cv2 drawing primitives are ~20% faster than PIL
# - cv2.GaussianBlur is ~8x faster than PIL.ImageFilter.GaussianBlur


@dataclass
class RenderConfig:
    """Configuration for the rendering engine.

    Parameters
    ----------
    noise_std : float
        Standard deviation of additive Gaussian noise. Default 3.0.
    shot_noise : bool
        Whether to apply Poisson (shot) noise. Default True.
    defocus_scale : float
        Blur radius per unit of Z distance from focus. Default 0.125.
        blur_radius = base_blur + abs(z) * defocus_scale
    base_blur : float
        Minimum blur radius (at perfect focus). Default 1.0.
    intensity_scale : float
        Base intensity multiplier. Default 1.0. This is multiplied by
        exposure_ms to determine final brightness scaling.
    background : int
        Background intensity level (0-255). Default 0.
    bit_depth : int
        Output bit depth (8 or 16). Default 8.
    random_seed : int | None
        Random seed for reproducible noise. Default None (random).
    backend : Backend
        Rendering backend: "auto" (default), "pil", or "cv2".
        "auto" uses cv2 if available, otherwise PIL.
        "cv2" raises ImportError if opencv-python is not installed.
    """

    noise_std: float = 3.0
    shot_noise: bool = True
    defocus_scale: float = 0.125
    base_blur: float = 1.0
    intensity_scale: float = 1.0
    background: int = 0
    bit_depth: int = 8
    random_seed: int | None = None
    backend: Backend = "auto"


@dataclass
class RenderEngine:
    """Engine for rendering sample objects based on microscope state.

    The render engine takes a list of sample objects and renders them into
    an image based on the current microscope state (stage position, exposure,
    pixel size, etc.).

    Parameters
    ----------
    objects : Sequence[SampleObject]
        List of sample objects to render.
    config : RenderConfig | None
        Rendering configuration. If None, uses default config.

    Examples
    --------
    >>> from pymmcore_plus.experimental.simulate import RenderEngine, Point, Line
    >>> engine = RenderEngine(
    ...     [
    ...         Point(0, 0, intensity=200),
    ...         Line((0, 0), (100, 100), intensity=100),
    ...     ]
    ... )
    >>> state = core.state()
    >>> image = engine.render(state)
    """

    objects: list[SampleObject]
    config: RenderConfig = field(default_factory=RenderConfig)
    _rng: np.random.Generator = field(default=None, repr=False)  # type: ignore

    def __post_init__(self) -> None:
        """Initialize random number generator."""
        self._rng = np.random.default_rng(self.config.random_seed)

    def _should_use_cv2(self) -> bool:
        """Determine whether to use cv2 backend based on config and availability."""
        backend = self.config.backend
        if backend == "pil":
            return False
        if backend in {"cv2", "auto"}:
            try:
                import cv2  # noqa: F401
            except ImportError:
                if backend == "cv2":
                    raise ImportError(
                        "opencv-python is required for backend='cv2'. "
                        "Install with: pip install opencv-python"
                    ) from None
            else:
                return True
        return False

    def render(self, state: SummaryMetaV1) -> np.ndarray:
        """Render the sample objects based on current microscope state.

        Parameters
        ----------
        state : SummaryMetaV1
            Current microscope state from `core.state()`.

        Returns
        -------
        np.ndarray
            Rendered image as numpy array with dtype matching bit_depth.
        """
        img_width, img_height = _img_width_height(state)
        pixel_size = _pixel_size(state)
        stage_x, stage_y, stage_z = _stage_position(state)
        exposure_ms = _exposure_ms(state)

        # Compute field of view in world coordinates
        fov_width = img_width * pixel_size
        fov_height = img_height * pixel_size
        left = stage_x - fov_width / 2
        top = stage_y - fov_height / 2
        fov_rect: Bounds = (left, top, left + fov_width, top + fov_height)

        # Scale factor: pixels per world unit
        scale = 1.0 / pixel_size

        # Transform function: world coords -> pixel coords
        def transform(x: float, y: float) -> tuple[int, int]:
            pixel_x = (x - left) / pixel_size
            pixel_y = (y - top) / pixel_size
            return int(pixel_x), int(pixel_y)

        # Render objects (returns float32 numpy array)
        if self._should_use_cv2():
            arr = self._render_objects_cv2(
                img_width, img_height, transform, scale, fov_rect
            )
        else:
            arr = self._render_objects_pil(
                img_width, img_height, transform, scale, fov_rect
            )

        # Apply physics effects
        arr = self._apply_defocus(arr, stage_z)
        arr = self._apply_exposure(arr, exposure_ms)
        arr = self._apply_noise(arr)

        # Convert to output format
        return self._finalize_image(arr)

    def _render_objects_cv2(
        self,
        width: int,
        height: int,
        transform: TransformFn,
        scale: float,
        fov_rect: Bounds,
    ) -> np.ndarray:
        """Render objects using OpenCV (faster)."""
        # Group objects by intensity for batch drawing
        intensity_groups: dict[int, list[SampleObject]] = defaultdict(list)
        for obj in self.objects:
            if obj.should_draw(fov_rect):
                intensity_groups[obj.intensity].append(obj)

        accumulator = np.zeros((height, width), dtype=np.float32)

        for _intensity, objs in intensity_groups.items():
            # Draw all objects with same intensity on one layer
            layer = np.zeros((height, width), dtype=np.uint8)
            for obj in objs:
                obj.draw_cv2(layer, transform, scale)
            accumulator += layer.astype(np.float32)

        return accumulator

    def _render_objects_pil(
        self,
        width: int,
        height: int,
        transform: TransformFn,
        scale: float,
        fov_rect: Bounds,
    ) -> np.ndarray:
        """Render objects using PIL, grouped by intensity for efficiency."""
        # Group objects by intensity for batch drawing
        intensity_groups: dict[int, list[SampleObject]] = defaultdict(list)
        for obj in self.objects:
            if obj.should_draw(fov_rect):
                intensity_groups[obj.intensity].append(obj)

        accumulator = np.zeros((height, width), dtype=np.float32)

        for _intensity, objs in intensity_groups.items():
            # Draw all objects with same intensity on one layer
            layer = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(layer)
            for obj in objs:
                obj.draw(draw, transform, scale)
            accumulator += np.asarray(layer, dtype=np.float32)

        return accumulator

    def _apply_defocus(self, arr: np.ndarray, z: float) -> np.ndarray:
        """Apply defocus blur based on Z position."""
        blur_radius = self.config.base_blur + abs(z) * self.config.defocus_scale
        if blur_radius <= 0:
            return arr

        arr_max = arr.max()
        if arr_max == 0:
            return arr

        if self._should_use_cv2():
            # cv2.GaussianBlur is ~8x faster than PIL
            import cv2

            ksize = int(blur_radius * 4) | 1  # kernel size must be odd
            sigma = blur_radius / 2
            return cv2.GaussianBlur(arr, (ksize, ksize), sigma)  # type: ignore [no-any-return]
        else:
            # Fall back to PIL
            normalized = (arr / arr_max * 255).astype(np.uint8)
            img = Image.fromarray(normalized, mode="L")
            blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            return np.asarray(blurred, dtype=np.float32) / 255 * arr_max  # type: ignore [no-any-return]

    def _apply_exposure(self, arr: np.ndarray, exposure_ms: float) -> np.ndarray:
        """Apply exposure time scaling."""
        # Scale intensity based on exposure (normalize to 100ms as "standard")
        scale = self.config.intensity_scale * (exposure_ms / 100.0)
        # In-place operations for speed
        arr *= scale
        arr += self.config.background
        return arr

    def _apply_noise(self, arr: np.ndarray) -> np.ndarray:
        """Apply shot noise and Gaussian noise."""
        # Shot noise (Poisson)
        if self.config.shot_noise:
            arr_max = arr.max()
            if arr_max > 0:
                # Poisson noise - variance equals mean
                np.maximum(arr, 0, out=arr)
                arr = self._rng.poisson(arr).astype(np.float32)

        # Gaussian read noise
        if self.config.noise_std > 0:
            arr += self._rng.normal(0, self.config.noise_std, arr.shape)

        return arr

    def _finalize_image(self, arr: np.ndarray) -> np.ndarray:
        """Convert to final output format."""
        max_val: int
        dtype: type[np.uint8] | type[np.uint16]
        if self.config.bit_depth == 16:
            max_val = 65535
            dtype = np.uint16
        else:
            max_val = 255
            dtype = np.uint8

        # Clip and normalize
        np.clip(arr, 0, None, out=arr)
        arr_max = arr.max()
        if arr_max > 0:
            arr *= max_val / arr_max

        return arr.astype(dtype)


# -----------------------------------------------------------------------------
# Helper functions to extract state from SummaryMetaV1
# -----------------------------------------------------------------------------


def _img_info(state: SummaryMetaV1) -> ImageInfo:
    """Get image info from state."""
    if not (img_infos := state.get("image_infos")):
        raise ValueError("No image info available in state.")
    return img_infos[0]


def _img_width_height(state: SummaryMetaV1) -> tuple[int, int]:
    """Get image dimensions from state."""
    img_info = _img_info(state)
    return img_info["width"], img_info["height"]


def _pixel_size(state: SummaryMetaV1) -> float:
    """Get pixel size (um/pixel) from state."""
    return _img_info(state)["pixel_size_um"]


def _stage_position(state: SummaryMetaV1) -> tuple[float, float, float]:
    """Get stage position (x, y, z) from state."""
    pos = state.get("position", {})
    return (pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0))


def _exposure_ms(state: SummaryMetaV1) -> float:
    """Get exposure time in milliseconds from state."""
    # Exposure might be in device properties
    for device in state.get("devices", ()):
        if device.get("type") == "Camera":
            for prop in device.get("properties", ()):
                if prop.get("name") == "Exposure":
                    val = prop.get("value")
                    if val is not None:
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
    # Default exposure
    return 100.0
