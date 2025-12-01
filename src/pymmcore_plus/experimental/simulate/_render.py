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
from typing import TYPE_CHECKING, no_type_check

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from pymmcore_plus.core._constants import Keyword

if TYPE_CHECKING:
    from typing_extensions import Literal, TypeAlias

    from pymmcore_plus.metadata.schema import DeviceInfo, SummaryMetaV1

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
    photon_flux : float
        Base photon flux in photons/pixel/second for intensity=255 objects.
        Default 1000. Combined with exposure time to determine photon count.
    shot_noise : bool
        Whether to apply Poisson (shot) noise. Default True.
    defocus_scale : float
        Blur radius per unit of Z distance from focus. Default 0.125.
        blur_radius = base_blur + abs(z) * defocus_scale
    base_blur : float
        Minimum blur radius (at perfect focus). Default 1.0.
    random_seed : int | None
        Random seed for reproducible noise. Default None (random).
    backend : Backend
        Rendering backend: "auto" (default), "pil", or "cv2".
        "auto" uses cv2 if available, otherwise PIL.
        "cv2" raises ImportError if opencv-python is not installed.
    """

    shot_noise: bool = True
    defocus_scale: float = 0.125
    base_blur: float = 1.5
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

    def _render_ground_truth(
        self, props: ImageProps, stage_x: float, stage_y: float
    ) -> np.ndarray:
        # Sample pixel size: how many µm in the sample each pixel represents
        # This accounts for both the physical sensor pixel size and magnification
        sample_pixel = props.sample_pixel_size  # pixel_size / magnification

        # Compute field of view (FOV) rectangle in sample/world coordinates
        # The FOV is centered on the stage position
        fov_width = props.img_width * sample_pixel  # width in µm
        fov_height = props.img_height * sample_pixel  # height in µm
        left = stage_x - fov_width / 2
        top = stage_y - fov_height / 2
        fov_rect: Bounds = (left, top, left + fov_width, top + fov_height)

        # Scale factor: how many pixels per µm (for scaling object sizes)
        scale = 1.0 / sample_pixel

        # Transform function: converts world coordinates (µm) to pixel coordinates
        def transform(x: float, y: float) -> tuple[int, int]:
            pixel_x = (x - left) / sample_pixel
            pixel_y = (y - top) / sample_pixel
            return int(pixel_x), int(pixel_y)

        # Draw all objects onto the image canvas
        # Intensity values (0-255) represent relative fluorophore density
        # This is the "ideal" sample without any optical or noise effects
        if self._should_use_cv2():
            density = self._render_objects_cv2(
                props.img_width, props.img_height, transform, scale, fov_rect
            )
        else:
            density = self._render_objects_pil(
                props.img_width, props.img_height, transform, scale, fov_rect
            )
        # density is now a float32 array with values typically 0-255
        # (can exceed 255 if objects overlap)
        return density

    def render(self, state: SummaryMetaV1) -> np.ndarray:
        """Render sample objects with physically realistic camera simulation.

        Parameters
        ----------
        state : SummaryMetaV1
            Current microscope state from `core.state()`.

        Returns
        -------
        np.ndarray
            Rendered image as uint8 (bit_depth <= 8) or uint16 (bit_depth > 8).
        """
        # Extract camera and optical properties from microscope state
        props = img_props(state)
        # Get current stage position in world coordinates (µm)
        stage_x, stage_y, stage_z = _stage_position(state)

        density = self._render_ground_truth(props, stage_x, stage_y)

        # Scale density to get photon emission rate for each pixel
        photon_flux = density * (props.photon_flux / 255.0)  # photons/second

        # This convolution preserves total flux (sum is conserved)
        photon_flux = self._apply_defocus(photon_flux, stage_z)

        # convert gain of -5 to 8 into analog gain multiplier, where 1 is unity
        analog_gain = 2.0**props.gain
        gray_values = simulate_camera(
            photons_per_second=photon_flux,
            exposure_ms=props.exposure_ms,
            read_noise=props.read_noise,
            ccd_binning=props.binning,
            bit_depth=props.bit_depth,
            offset=int(props.offset),
            rnd=self._rng,
            analog_gain=analog_gain,
            qe=props.qe,
            full_well=props.full_well_capacity,
            add_poisson=self.config.shot_noise,
        )
        return gray_values

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

        if self._should_use_cv2():
            import cv2

            ksize = int(blur_radius * 6) | 1  # kernel size must be odd
            return cv2.GaussianBlur(arr, (ksize, ksize), blur_radius)  # type: ignore [no-any-return]
        else:
            img = Image.fromarray(arr, mode="F")
            blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            return np.asarray(blurred, dtype=np.float32)


# -----------------------------------------------------------------------------
# Helper functions to extract state from SummaryMetaV1
# -----------------------------------------------------------------------------


def _stage_position(state: SummaryMetaV1) -> tuple[float, float, float]:
    """Get stage position (x, y, z) from state."""
    pos = state.get("position", {})
    return (pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0))


def _get_core(state: SummaryMetaV1) -> DeviceInfo:
    """Get Core device info from state."""
    return next(
        dev
        for dev in state.get("devices", ())
        if dev.get("label") == Keyword.CoreDevice
    )


def _get_camera(state: SummaryMetaV1) -> DeviceInfo | None:
    """Get Camera device info from state."""
    core = _get_core(state)
    for prop in core["properties"]:
        if prop["name"] == "Camera":
            camera_label = prop["value"]
            break
    else:
        return None
    return next((dev for dev in state["devices"] if dev["label"] == camera_label), None)


@dataclass
class ImageProps:
    """Camera and optical properties extracted from device state.

    These properties describe both the camera sensor characteristics and
    the optical system configuration needed to simulate realistic images.

    Attributes
    ----------
    exposure_ms : float
        Exposure time in milliseconds. Default 10.0.
    offset : float
        Digital offset (bias) in gray levels (ADU). Default 100.
    gain : float
        Camera gain setting (raw value, typically -5 to 8). Default 0.0.
        At gain=0 (unity), full_well_capacity electrons map to max gray value.
        Positive gain = earlier saturation (more amplification).
        Negative gain = later saturation (less amplification).
    bit_depth : int
        Camera bit depth. Default 16.
    read_noise : float
        Read noise in electrons RMS. Default 2.5.
    img_width : int
        Image width in pixels. Default 512.
    img_height : int
        Image height in pixels. Default 512.
    binning : int
        Pixel binning factor. Default 1.
    photon_flux : float
        Peak photon emission rate in photons/pixel/second for intensity=255
        fluorophores. Default 1000.
    pixel_size : float
        Physical pixel size on the camera sensor in micrometers. Default 6.5.
    magnification : float
        Objective magnification. Default 20.0.
    full_well_capacity : float
        Full well capacity in electrons. Default 18000.
    qe : float
        Quantum efficiency (fraction of photons converted to electrons). Default 0.8.
    """

    exposure_ms: float = 10.0
    offset: float = 100.0  # small baseline to capture read noise symmetry
    gain: float = 0.0  # raw gain setting, NOT 2^gain
    bit_depth: int = 16
    read_noise: float = 2.5
    img_width: int = 512
    img_height: int = 512
    binning: int = 1
    photon_flux: float = 1000.0
    pixel_size: float = 6.5  # physical sensor pixel size (µm)
    magnification: float = 20.0
    full_well_capacity: float = 18000.0
    qe: float = 0.8

    @property
    def sample_pixel_size(self) -> float:
        """Effective pixel size in sample space (µm/pixel)."""
        return self.pixel_size / self.magnification


@no_type_check
def img_props(state: SummaryMetaV1) -> ImageProps:
    """Extract camera and optical properties from device state.

    Reads camera properties from the state dict and returns an ImageProps
    dataclass with all relevant parameters for image simulation.
    """
    props: dict[str, float | int] = {}

    # Get camera properties
    if camera := _get_camera(state):
        for prop in camera["properties"]:
            name = prop["name"]
            value = prop["value"]
            if name == "Exposure":
                props["exposure_ms"] = float(value)
            elif name == "Offset":
                props["offset"] = float(value)
            elif name == "Gain":
                # Store raw gain setting (not 2^gain)
                # Unity gain (0) maps FWC to max gray value
                props["gain"] = float(value)
            elif name == "BitDepth":
                props["bit_depth"] = int(value)
            elif name == "ReadNoise (electrons)":
                props["read_noise"] = float(value)
            elif name == "OnCameraCCDXSize":
                props["img_width"] = int(value)
            elif name == "OnCameraCCDYSize":
                props["img_height"] = int(value)
            elif name == "Binning":
                props["binning"] = int(value)
            elif name == "Photon Flux":
                # DemoCamera's Photon Flux is too low for realistic simulation
                # i think it's modeling at the camera, rather than from the sample
                # Scale up by 100x to get reasonable signal at typical exposures
                props["photon_flux"] = float(value) * 100
            elif name == "Full Well Capacity":
                props["full_well_capacity"] = float(value)
            elif name == "Quantum Efficiency":
                props["qe"] = float(value)

    if props.get("bit_depth") and props["bit_depth"] < 10:
        props["offset"] = 10.0  # lower offset for low bit depth cameras

    return ImageProps(**props)


def simulate_camera(
    photons_per_second: np.ndarray,
    exposure_ms: float,
    read_noise: float,
    bit_depth: int,
    offset: int,
    rnd: np.random.Generator,
    analog_gain: float = 1.0,
    em_gain: float = 1.0,
    ccd_binning: int = 1,
    qe: float = 1,
    full_well: float = 18000,
    serial_reg_full_well: float | None = None,
    dark_current: float = 0.0,
    add_poisson: bool = True,
) -> np.ndarray:
    if analog_gain <= 0:
        raise ValueError("gain_multiplier must be positive")

    # restrict to positive values
    exposure_s = exposure_ms / 1000
    incident_photons = np.maximum(photons_per_second * exposure_s, 0)

    # combine signal and dark current into single poisson sample
    detected_photons = incident_photons * qe
    avg_dark_e = dark_current * exposure_s

    if add_poisson:
        # Single Poisson sample combining both sources
        total_electrons: np.ndarray = rnd.poisson(detected_photons + avg_dark_e)
    else:
        # Just the mean values
        total_electrons = detected_photons + avg_dark_e

    # cap total electrons to full-well-capacity
    total_electrons = np.minimum(total_electrons, full_well)

    if (b := ccd_binning) > 1:
        # Hardware binning: sum electrons from NxN blocks
        # Reshape to create blocks
        new_h = total_electrons.shape[0] // b
        new_w = total_electrons.shape[1] // b
        cropped = total_electrons[: new_h * b, : new_w * b]
        # Sum over binning blocks
        binned_electrons = cropped.reshape(new_h, b, new_w, b).sum(axis=(1, 3))
    else:
        binned_electrons = total_electrons

    if em_gain > 1.0:
        # Gamma distribution models the stochastic multiplication
        # Only apply to pixels with signal
        amplified = np.zeros_like(binned_electrons, dtype=float)
        mask = binned_electrons > 0
        amplified[mask] = rnd.gamma(shape=binned_electrons[mask], scale=em_gain)
        binned_electrons = amplified

    # cap total electrons to serial register full-well-capacity
    if serial_reg_full_well is not None:
        binned_electrons = np.minimum(binned_electrons, serial_reg_full_well)
        effective_full_well = serial_reg_full_well
    else:
        effective_full_well = full_well * (ccd_binning**2)

    # Add read noise (Gaussian, in electrons)
    if read_noise > 0:
        binned_electrons += rnd.normal(0, read_noise, size=binned_electrons.shape)

    # unity gain is gain at which full well maps to max gray value
    unity_gain = effective_full_well / (2**bit_depth - 1)
    # actual gain considering analog gain setting.  Final e-/ADU
    actual_gain = unity_gain / analog_gain
    # Convert to ADU with offset
    adu = (binned_electrons / actual_gain) + offset
    # Quantize/clip to bit depth
    adu = np.clip(adu, 0, 2**bit_depth - 1)

    # Final integer image
    gray_values = np.round(adu).astype(np.uint16 if bit_depth > 8 else np.uint8)
    return gray_values  # type: ignore [no-any-return]
