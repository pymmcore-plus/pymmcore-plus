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
    base_blur: float = 1.0
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
        """Render sample objects with physically realistic camera simulation.

        Physical Model Overview
        -----------------------
        1. **Geometry**: Determine field of view using camera dimensions, pixel size,
           binning, and magnification. Sample pixel size = phys_pixel / magnification.

        2. **Ground truth**: Render objects as fluorophore density (0-255 intensity).

        3. **Emission**: Convert density to photon flux (photons/pixel/second).

        4. **Optics**: Apply PSF blur (Gaussian). Preserves total flux.

        5. **Detection**: Integrate photon flux over exposure time → photon count.

        6. **Conversion**: Photons → electrons via quantum efficiency (QE).

        7. **Shot noise**: Apply Poisson statistics to electron counts.

        8. **Saturation**: Clip electrons to full well capacity (FWC).

        9. **Read noise**: Add Gaussian read noise (in electrons).

        10. **Digitization**: Convert electrons → ADU using gain, add offset, clip.

        Parameters
        ----------
        state : SummaryMetaV1
            Current microscope state from `core.state()`.

        Returns
        -------
        np.ndarray
            Rendered image as uint8 (bit_depth <= 8) or uint16 (bit_depth > 8).
        """
        # =====================================================================
        # STEP 1: GEOMETRY - Determine image shape and coordinate transform
        # =====================================================================
        # Extract camera and optical properties from microscope state
        props = img_props(state)

        # Sample pixel size: how many µm in the sample each pixel represents
        # This accounts for both the physical sensor pixel size and magnification
        # With binning, effective pixels are larger on the sensor
        sample_pixel = props.sample_pixel_size  # (pixel_size * binning) / magnification

        # Get current stage position in world coordinates (µm)
        stage_x, stage_y, stage_z = _stage_position(state)

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

        # =====================================================================
        # STEP 2: GROUND TRUTH - Render fluorophore density
        # =====================================================================
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

        # =====================================================================
        # STEP 3: EMISSION - Convert density to photon flux
        # =====================================================================
        # photon_flux (from ImageProps) is the emission rate for intensity=255
        # in units of photons/pixel/second
        # Scale density to get photon emission rate for each pixel
        photon_flux = density * (props.photon_flux / 255.0)
        # photon_flux is now in photons/pixel/second

        # =====================================================================
        # STEP 4: OPTICS - Apply point spread function (PSF) blur
        # =====================================================================
        # The PSF spreads light from each point source across neighboring pixels
        # Blur increases with defocus (distance from focal plane)
        # IMPORTANT: This convolution preserves total flux (sum is conserved)
        photon_flux = self._apply_defocus(photon_flux, stage_z)

        # =====================================================================
        # STEP 5: DETECTION - Integrate flux over exposure time
        # =====================================================================
        # Total photons collected = flux (photons/s) * exposure time (s)
        exposure_s = props.exposure_ms / 1000.0
        photons = photon_flux * exposure_s
        # photons is now total photon count per pixel

        # =====================================================================
        # STEP 6: CONVERSION - Photons to electrons via quantum efficiency
        # =====================================================================
        # QE is the fraction of incident photons that produce photoelectrons
        # Typical scientific cameras have QE of 0.6-0.95
        electrons = photons * props.qe
        # electrons is now the expected electron count per pixel

        # =====================================================================
        # STEP 7: SHOT NOISE - Apply Poisson statistics
        # =====================================================================
        # Shot noise arises from the discrete nature of photon detection
        # Variance = mean for Poisson distribution (sqrt(N) noise)
        if self.config.shot_noise:
            np.maximum(electrons, 0, out=electrons)  # Poisson requires non-negative
            electrons = self._rng.poisson(electrons).astype(np.float32)

        # =====================================================================
        # STEP 8: SATURATION - Clip to full well capacity
        # =====================================================================
        # Each pixel can only hold a finite number of electrons (FWC)
        # Excess electrons are lost (blooming ignored in this simple model)
        np.clip(electrons, 0, props.full_well_capacity, out=electrons)

        # =====================================================================
        # STEP 9: READ NOISE - Add Gaussian noise during readout
        # =====================================================================
        # Read noise is added during the charge-to-voltage conversion
        # It's independent of signal level and specified in electrons RMS
        if props.read_noise > 0:
            electrons += self._rng.normal(0, props.read_noise, electrons.shape)

        # =====================================================================
        # STEP 10: DIGITIZATION - Convert electrons to ADU (gray levels)
        # =====================================================================
        # The ADC converts the analog electron signal to digital counts (ADU)

        # Gain determines the electrons-to-ADU conversion:
        # - At unity gain (gain=0): FWC electrons → max gray value
        # - Positive gain: more amplification, saturate at fewer electrons
        # - Negative gain: less amplification, need more electrons to saturate
        adu = electrons * props.adu_per_electron

        # Add digital offset (bias level)
        # This ensures the baseline is above zero to preserve read noise symmetry
        adu += props.offset

        # Final clipping to valid ADU range [0, max_gray]
        np.clip(adu, 0, props.max_gray, out=adu)

        # Convert to appropriate integer dtype based on bit depth
        dtype = np.uint16 if props.bit_depth > 8 else np.uint8
        return adu.astype(dtype)  # type: ignore [no-any-return]

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
            import cv2

            ksize = int(blur_radius * 6) | 1  # kernel size must be odd
            return cv2.GaussianBlur(arr, (ksize, ksize), blur_radius)  # type: ignore [no-any-return]
        else:
            normalized = (arr / arr_max * 255).astype(np.uint8)
            img = Image.fromarray(normalized)
            blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            return np.asarray(blurred, dtype=np.float32) / 255 * arr_max  # type: ignore [no-any-return]


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
    effective_pixel_size: float | None = None  # from MM pixel size config

    @property
    def sample_pixel_size(self) -> float:
        """Effective pixel size in sample space (µm/pixel).

        If effective_pixel_size is set (from Micro-Manager's pixel size
        configuration), uses that directly. Otherwise computes from
        physical sensor pixel size, binning, and magnification:
        sample_pixel_size = (pixel_size * binning) / magnification
        """
        if self.effective_pixel_size is not None:
            return self.effective_pixel_size
        return (self.pixel_size * self.binning) / self.magnification

    @property
    def max_gray(self) -> int:
        """Maximum gray value for the bit depth: 2^bit_depth - 1."""
        return (1 << self.bit_depth) - 1

    @property
    def adu_per_electron(self) -> float:
        """Conversion factor from electrons to ADU (gray levels).

        At unity gain (gain=0), full_well_capacity maps to max_gray.
        Positive gain amplifies (saturate earlier), negative attenuates.

        adu_per_electron = (max_gray / full_well_capacity) * 2^gain
        """
        unity_gain = self.max_gray / self.full_well_capacity
        return unity_gain * (2.0**self.gain)  # type: ignore [no-any-return]


@no_type_check
def img_props(state: SummaryMetaV1) -> ImageProps:
    """Extract camera and optical properties from device state.

    Reads camera properties from the state dict and returns an ImageProps
    dataclass with all relevant parameters for image simulation.

    The sample pixel size (effective_pixel_size) is read from image_infos
    if available, which represents the already-computed pixel size in sample
    space (accounting for magnification, binning, etc. via Micro-Manager's
    pixel size configuration).
    """
    props: dict[str, float | int] = {}

    # Get image dimensions and pixel size from image_infos
    if img_infos := state.get("image_infos"):
        info = img_infos[0]
        props["img_width"] = info["width"]
        props["img_height"] = info["height"]
        # pixel_size_um is the effective sample pixel size from MM config
        # This already accounts for magnification and binning
        if "pixel_size_um" in info:
            props["effective_pixel_size"] = float(info["pixel_size_um"])

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
                # Only use if not already set from image_infos
                if "img_width" not in props:
                    props["img_width"] = int(value)
            elif name == "OnCameraCCDYSize":
                if "img_height" not in props:
                    props["img_height"] = int(value)
            elif name == "Binning":
                props["binning"] = int(value)
            elif name == "Photon Flux":
                # DemoCamera's Photon Flux is too low for realistic simulation
                # Scale up by 100x to get reasonable signal at typical exposures
                props["photon_flux"] = float(value) * 100
            elif name == "Full Well Capacity":
                props["full_well_capacity"] = float(value)
            elif name == "Quantum Efficiency":
                props["qe"] = float(value)

    if props.get("bit_depth") and props["bit_depth"] < 10:
        props["offset"] = 10.0  # lower offset for low bit depth cameras
    return ImageProps(**props)
