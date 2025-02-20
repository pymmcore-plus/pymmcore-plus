from __future__ import annotations

import contextlib
import sys
import warnings
from typing import TYPE_CHECKING, Iterable, Iterator, Literal

import numpy as np
from psygnal import Signal

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pymmcore_plus import CMMCorePlus

    WindowType = Literal["hanning", "blackman", None]
    SubpixelType = Literal["parabolic", "upsampled", None]


class AutoCameraCalibrator:
    """Calibrates the pixel size and rotation of a camera.

    This class uses phase correlation to estimate the pixel size and rotation of a
    camera. It captures images at different stage positions and calculates the pixel
    shifts between the images. It then uses these shifts to calculate the pixel size and
    rotation.  Use `calibrate` to perform the calibration and `affine` to get the
    calibration matrix (can be called during the calibration process to get the
    calibration matrix at any point, but care should be taken to call affine in a try
    block, as it will raise an error if no pixel shifts have been recorded yet, or an
    error if the affine matrix is singular).

    Parameters
    ----------
    core : CMMCorePlus
        The CMMCorePlus instance to use for capturing images and moving the stage.
    stage_device : str, optional
        The name of the stage device to use for moving the stage. If None, the core will
        use the current XY stage device.
    camera_device : str, optional
        The name of the camera device to use for capturing images. If None, the core
        will use the current camera device.
    roi : tuple[int, int, int, int], optional
        The region of interest to capture from the camera. (x, y, width, height). If
        None the entire image will be used.
    max_distance : int, optional
        The maximum distance to move the stage in each direction. This should be no more
        than half the image size, to avoid FFT aliasing. Default is 50.
    num_steps : int, optional
        The number of steps to take between 0 and max_distance. Default is 5.

    Attributes
    ----------
    shift_acquired : Signal
        Signal emitted when a new pixel shift is acquired during calibration.  Can be
        connected to a callback function to perform custom actions after each shift is
        acquired.
    last_correlation : np.ndarray | None
        The last correlation matrix acquired during calibration. This can be used for
        debugging or visualization purposes.
    """

    shift_acquired: Signal = Signal()
    calibration_complete: Signal = Signal()

    def __init__(
        self,
        core: CMMCorePlus,
        *,
        stage_device: str | None = None,
        camera_device: str | None = None,
        roi: tuple[int, int, int, int] | None = None,
        # max distance should be no more than half the image size, to avoid FFT aliasing
        # the user can either enter this, or we could conceivably calculate it after the
        # first estimate of the pixel shift is calculated in `calibrate`.
        max_distance: int = 50,
        num_steps: int = 5,
        max_shear_tolerance: float = 0.05,
        fft_window: WindowType = "hanning",
        subpixel_method: SubpixelType = "parabolic",
        maximum_safe_radius: float = 1000,
    ) -> None:
        self.core = core
        self.roi = roi
        self.stage_device = stage_device
        self.camera_device = camera_device
        self.maximum_safe_radius = maximum_safe_radius

        # last correlation matrix acquired, for debugging
        self.last_correlation: np.ndarray | None = None
        # last fit residuals, for debugging
        self._residuals: np.ndarray | None = None

        # pixel shifts for each stage move, accumulated during calibration
        # mapping of {(dx_stage, dy_stage) -> (dx_pixel, dy_pixel)}
        self._point_pairs: dict[tuple[float, float], tuple[float, float]] = {}

        # cached affine transform that maps pixel shifts to stage shifts
        self._cached_affine: np.ndarray | None = None

        # maximum distance to move in each direction from initial position
        self._max_distance = max_distance
        # number of steps to take between 0 and max_distance
        self._num_steps = num_steps
        # maximum shear tolerance, used to warn if the shear factor is too high
        self._max_shear_tolerance = max_shear_tolerance
        self._window = fft_window
        self._subpixel_method = subpixel_method
        self._max_step = 0.25

    def _capture_roi(self) -> np.ndarray:
        """Capture an image and crop to ROI if one was provided."""
        ctx = (
            self.core.setContext(cameraDevice=self.camera_device)
            if self.camera_device
            else contextlib.nullcontext()
        )
        with ctx:
            img = self.core.snap().astype(np.float32)

        if self.roi is not None:
            x, y, w, h = self.roi
            try:
                img = img[y : y + h, x : x + w]
            except IndexError:  # pragma: no cover
                warnings.warn(
                    "ROI is out of bounds of the image. Please check the ROI values. "
                    "Falling back to the full image.",
                    stacklevel=2,
                )
                self.roi = None
        return img

    def _move_to(self, x: float, y: float) -> None:
        if self.stage_device:
            self.core.setXYPosition(self.stage_device, x, y)
        else:
            self.core.setXYPosition(x, y)
        self.core.waitForSystem()

    def _iter_positions(self) -> Iterator[tuple[float, float]]:
        # take a -2 micron initial step in the X direction, to get a pixel estimate
        yield (-2, 0)
        # get current pix estimate and step 20 pixels in the other X & Y directions
        # to form a triangle with the initial point
        px_estimate = self.pixel_size(from_affine=False)
        if px_estimate > 2:
            warnings.warn(
                "Pixel size estimate is very large. This may indicate a problem with "
                "the calibration. Please check the calibration images and ROI.",
                stacklevel=2,
            )
            return
        yield (20 * px_estimate, 20 * px_estimate)
        # we now have 3 points. Grab the new pixel size estimate and estimate the
        # field-of-view size
        px_estimate = self.pixel_size(from_affine=False)
        half_fov = np.array(self.last_correlation.shape) * px_estimate * 0.5

        # yield stage positions at 3 extreme corners of the field of view
        max_step = self._max_step
        yield (half_fov[1] * max_step * 0.5, -half_fov[0] * max_step * 0.5)
        yield (-half_fov[1] * max_step * 0.5, -half_fov[0] * max_step * 0.5)
        yield (-half_fov[1] * max_step * 0.5, half_fov[0] * max_step * 0.5)
        yield (half_fov[1] * max_step * 0.5, half_fov[0] * max_step * 0.5)
        yield (half_fov[1] * max_step, -half_fov[0] * max_step)
        yield (-half_fov[1] * max_step, -half_fov[0] * max_step)
        yield (-half_fov[1] * max_step, half_fov[0] * max_step)
        yield (half_fov[1] * max_step, half_fov[0] * max_step)

    def calibrate(
        self, moves: Iterable[tuple[float, float]] | None = None
    ) -> np.ndarray:
        """Calibrate the pixel size and rotation of the camera.

        1. Capture a reference image at the initial stage position.
        2. For each (dx, dy) in moves:
            a. Move the stage to initial + (dx, dy).
            b. Capture a new image (crop to ROI if provided).
            c. Calculate the pixel shift between the reference image and the new image.
        3. Warn if the shear factor is greater than 0.05.
        4. Return the affine transform that maps pixel shifts to stage shifts.

        Parameters
        ----------
        moves : list of (dx, dy), optional
            The stage moves to make, relative to the initial position.
            If None, a default set of moves will be used, based on the max_distance and
            num_steps parameters provided to the constructor.

        Returns
        -------
        np.ndarray
            A 3x3 affine transform that maps pixel shifts to stage shifts.
            2x2 submatrix is the linear transformation, the last row is always [0, 0, 1]
            and the last column is always [0, 0, 1] (no translation).
        """
        # Capture reference image at initial stage position.
        if self.stage_device:
            x_initial, y_initial = self.core.getXYPosition(self.stage_device)
        else:
            x_initial, y_initial = self.core.getXYPosition()

        ref = self._capture_roi()

        if moves is None:
            moves = self._iter_positions()

        # For each known stage move, capture a new image and measure pixel displacement.
        self._point_pairs.clear()
        for dx_stage, dy_stage in moves:
            new_stage = (x_initial + dx_stage, y_initial + dy_stage)
            # check magnitude of move:
            if np.linalg.norm((dx_stage, dy_stage)) > self.maximum_safe_radius:
                raise ValueError(
                    f"Requested stage move ({dx_stage}, {dy_stage}) is too large. "
                    f"Maximum safe radius is {self.maximum_safe_radius}."
                )

            self._move_to(*new_stage)
            img = self._capture_roi()
            pixel_shifts, self.last_correlation = measure_image_displacement(
                ref, img, window=self._window, subpixel_method=self._subpixel_method
            )
            self._point_pairs[(dx_stage, dy_stage)] = pixel_shifts
            self.shift_acquired.emit()
            # clear this on each step in case a callback accesses .affine
            self._cached_affine = None

        # Return the affine transform that maps pixel shifts to stage shifts.
        affine = self.affine()
        # warn on high shear:
        if (shear := self.shear()) > self._max_shear_tolerance:
            warnings.warn(
                f"High shear detected: {shear:.3f}. This may indicate a non-linear "
                "relationship between stage and pixel shifts.",
                stacklevel=2,
            )
        self.calibration_complete.emit()
        return affine

    def pixel_shifts(self) -> Iterable[tuple[tuple[float, float], tuple[float, float]]]:
        """Returns the pixel shifts acquired during calibration.

        Each item is a 2-tuple with the stage coordinates and the corresponding
        measured pixel shift: ((dx_stage, dy_stage), (dx_pixel, dy_pixel)).
        """
        yield from self._point_pairs.items()

    def affine(self) -> np.ndarray:
        """Returns the current affine transform.

        The value is cached after the first call, and is cleared whenever a new pixel
        shift is acquired during calibration.
        """
        # Solve for the pure linear transformation A (a 2x2 matrix) that maps pixel
        # shifts to stage shifts. That is, we want: stage_shifts @ A = pixel_shifts
        if self._cached_affine is None:
            if not self._point_pairs:  # pragma: no cover
                raise RuntimeError(
                    "No pixel shifts have been recorded. Run calibrate() first."
                )
            _stage_shifts, _pixel_shifts = zip(*self._point_pairs.items())
            # add (0, 0) to each:
            stage_shifts = np.vstack([(0, 0), _stage_shifts])
            pixel_shifts = np.vstack([(0, 0), _pixel_shifts])
            # Computes the vector `x` that approximately solves the equation
            # ``pixel_shifts @ x = stage_shifts``.
            # note this is the INVERSE matrix mapping pixel shifts to stage shifts
            A, res = np.linalg.lstsq(pixel_shifts, stage_shifts)[:2]
            self._residuals = res
            if np.linalg.det(A) == 0:
                warnings.warn(
                    "Singular matrix detected. Affine transform may be invalid.",
                    stacklevel=2,
                )

            # Construct the full 2D affine transform. A is 2 x 2
            affine = np.eye(3, dtype=np.float32)
            affine[:2, :2] = A
            self._cached_affine = affine
        return self._cached_affine

    def pixel_size(self, from_affine: bool | None = None) -> float:
        """Returns the pixel size in microns.

        If `from_affine` is True, the pixel size is calculated from the affine matrix.
        otherwise, it is based on the average ratio of the stage shifts to pixel shifts.

        """
        if from_affine is None:
            from_affine = len(self._point_pairs) > 3

        if from_affine:
            try:
                return float(np.linalg.norm(self.affine()[0, 0:2]))
            except Exception as e:
                warnings.warn(
                    f"Error calculating pixel size from affine matrix: {e}. "
                    "Falling back to ratio of stage shifts to pixel shifts.",
                    stacklevel=2,
                )

        return self._mean_vectorial_displacement()

    def _mean_vectorial_displacement(self) -> float:
        """Returns the mean ratio of the magnitude of stage shifts to pixel shifts."""
        estimates = []
        for stage_shift, pixel_shift in self._point_pairs.items():
            estimates.append(np.linalg.norm(stage_shift) / np.linalg.norm(pixel_shift))
        return float(np.mean(estimates))

    def rotation(self) -> float:
        """Returns the rotation in degrees."""
        affine = self.affine()
        return float(np.rad2deg(np.arctan2(affine[1, 0], affine[0, 0])))

    def shear(self) -> float:
        """Returns the shear factor."""
        M = self.affine()[:2, :2]
        # Compute the scale factor along the x-axis.
        scale_x = np.sqrt(M[0, 0] ** 2 + M[1, 0] ** 2)
        if scale_x == 0:
            raise ValueError("Invalid affine matrix: zero x-scale.")
        shear = (M[0, 0] * M[0, 1] + M[1, 0] * M[1, 1]) / (scale_x**2)
        return float(shear)


def measure_image_displacement(
    img1: np.ndarray,
    img2: np.ndarray,
    window: WindowType = "hanning",
    subpixel_method: SubpixelType = "parabolic",
) -> tuple[tuple[float, float], np.ndarray]:
    """Estimates the translation shift between two images using phase correlation.

    Parameters
    ----------
    img1 : np.ndarray
        The first image.
    img2 : np.ndarray
        The second image.
    window : Literal["hanning", "blackman", None]
        The windowing function to apply to the images before computing the FFT.
        Can be "hanning", "blackman" or None.  Hanning is a good default, but blackman
        may be better for images with high-frequency noise.
        None will apply no windowing. Default is "hanning".
    subpixel_method : Literal["parabolic", "upsampled", None]
        The subpixel refinement method to use.
        "parabolic" uses a parabolic fit (fast, works when the peak is well-defined)
        "upsampled" uses an upsampled cross-correlation method (more precise at the cost
        of additional computation), recommended for critical subpixel accuracy.
        Default is "parabolic".

    Returns
    -------
    tuple[tuple[float, float], np.ndarray]
        The estimated shift in pixels (x, y) and the correlation matrix (which may
        be useful for debugging or visualization).
    """
    correlation = phase_correlate(img1, img2, window)

    # mask out DC component
    correlation[correlation.shape[0] // 2, correlation.shape[1] // 2] = 0
    # blur slightly to reduce noise
    correlation = _smooth_image(correlation, kernel_size=3)

    # Find the peak location and calculate the shift.
    peak_idx = np.unravel_index(np.argmax(correlation), correlation.shape)
    print("peak_idx", peak_idx)
    # calculate the shift from the center of the image
    center = np.asarray(correlation.shape) // 2
    shift = np.asarray(peak_idx) - center

    # Subpixel refinement based on the chosen method.
    if subpixel_method == "parabolic":
        sub_y, sub_x = _parabolic_subpixel(correlation, peak_idx)
    elif subpixel_method == "upsampled":
        sub_y, sub_x = _upsampled_subpixel(correlation, peak_idx)
    elif subpixel_method is None:
        sub_y, sub_x = 0.0, 0.0
    else:  # pragma: no cover
        raise ValueError("subpixel_method must be 'parabolic' or 'upsampled' or None.")

    # note the swapping of YX -> XY
    return (float(shift[1] + sub_x), float(shift[0] + sub_y)), correlation


def phase_correlate(
    img1: np.ndarray, img2: np.ndarray, window: WindowType = "hanning"
) -> np.ndarray:
    """Returns the phase correlation matrix between two images."""
    if not img1.shape == img2.shape:  # pragma: no cover
        raise ValueError("Input images must have the same shape.")

    # convert RGB to grayscale by averaging over the color channels
    if img1.ndim == 3:
        img1 = np.mean(img1, axis=-1)
    if img2.ndim == 3:
        img2 = np.mean(img2, axis=-1)

    if img1.ndim != 2 or img2.ndim != 2:  # pragma: no cover
        raise ValueError("Input images must be 2D or 3D (RGB).")

    # subtract mean to remove DC component
    img1 = img1.astype(np.float32)
    img1 -= np.mean(img1)
    img2 = img2.astype(np.float32)
    img2 -= np.mean(img2)

    # apply windowing function
    img1 = _window(img1, window)
    img2 = _window(img2, window)

    # Compute FFTs of the two images.
    F1 = np.fft.fft2(img1)
    F2 = np.fft.fft2(img2)

    # Compute normalized cross-power spectrum.
    R = F1 * np.conjugate(F2)
    # normalize by magnitude, avoiding division by zero
    R /= np.abs(R) + sys.float_info.epsilon

    # Inverse FFT to get correlation; shift the zero-frequency component to center.
    corr = np.fft.ifft2(R)
    corr = np.fft.fftshift(corr)
    return np.abs(corr)


def _window(img: np.ndarray, window: WindowType = "hanning") -> np.ndarray:
    """Applies a windowing function to an image."""
    if window is None:
        return img
    if window == "hanning":
        _window = np.hanning(img.shape[0])[:, None] * np.hanning(img.shape[1])
    elif window == "blackman":
        _window = np.blackman(img.shape[0])[:, None] * np.blackman(img.shape[1])
    elif window != "none":  # pragma: no cover
        raise ValueError("'window' must be one of 'hanning', 'blackman' or None.")
    return img * _window


def _parabolic_subpixel(
    corr: np.ndarray, peak: tuple[np.signedinteger, ...]
) -> tuple[float, float]:
    """Subpixel refinement of a peak location in a 2D array."""
    py, px = peak[:2]
    sub_y, sub_x = 0.0, 0.0
    center_val = corr[py, px]

    # Check if the peak is not on the border for x direction
    if 0 < px < corr.shape[1] - 1:
        # Get the values to the left and right of the peak
        left = corr[py, px - 1]
        right = corr[py, px + 1]
        # Calculate the denominator for the parabolic fit
        denom = 2 * center_val - left - right
        # If the denominator is not zero, calculate the subpixel shift in x direction
        if denom != 0:
            sub_x = (left - right) / (2 * denom)

    # Check if the peak is not on the border for y direction
    if 0 < py < corr.shape[0] - 1:
        top = corr[py - 1, px]
        bottom = corr[py + 1, px]
        denom = 2 * center_val - top - bottom
        if denom != 0:
            sub_y = (top - bottom) / (2 * denom)

    return sub_y, sub_x


def _upsampled_subpixel(
    corr: np.ndarray,
    peak: tuple[np.signedinteger, ...],
    upsample_factor: int = 10,
    size: int = 5,
) -> tuple[float, float]:
    """
    Refines the peak location by upsampling the correlation around the peak
    using FFT zero-padding (without scipy.ndimage).

    Parameters
    ----------
    corr : NDArray[np.float_]
        The correlation matrix.
    peak : tuple[int, int]
        The integer coordinates of the peak (y, x).
    upsample_factor : int, optional
        Factor by which to upsample the region around the peak.
    size : int, optional
        The size of the region (in original pixels) to extract around the peak.

    Returns
    -------
    tuple[float, float]
        Subpixel adjustments (dy, dx) to add to the integer peak location.
    """
    py, px = peak[:2]
    half_size = size // 2

    # Define the window region around the peak, ensuring we don't exceed array bounds.
    y0 = np.maximum(py - half_size, 0)
    y1 = np.minimum(py + half_size + 1, corr.shape[0])
    x0 = np.maximum(px - half_size, 0)
    x1 = np.minimum(px + half_size + 1, corr.shape[1])
    window = corr[y0:y1, x0:x1]
    m, n = window.shape

    # Compute the FFT of the window.
    window_fft = np.fft.fft2(window)

    # Zero-pad the FFT to upsample.
    M, N = m * upsample_factor, n * upsample_factor
    padded_fft = np.zeros((M, N), dtype=complex)
    start_y = (M - m) // 2
    start_x = (N - n) // 2
    padded_fft[start_y : start_y + m, start_x : start_x + n] = window_fft

    # Compute the inverse FFT to obtain the upsampled correlation.
    upsampled = np.fft.ifft2(padded_fft)
    upsampled = np.abs(upsampled)

    # Locate the peak in the upsampled correlation.
    up_peak_idx = np.unravel_index(np.argmax(upsampled), upsampled.shape)
    up_peak_y, up_peak_x = up_peak_idx

    # The center of the upsampled window corresponds to the original integer peak.
    center_upsampled = np.array(upsampled.shape) / 2
    sub_y = (up_peak_y - center_upsampled[0]) / upsample_factor
    sub_x = (up_peak_x - center_upsampled[1]) / upsample_factor
    return sub_y, sub_x


def _smooth_image(img: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view

    # Create a uniform averaging kernel
    kernel = np.ones((kernel_size, kernel_size)) / (kernel_size**2)
    pad_size = kernel_size // 2
    # Reflect padding to avoid boundary artifacts
    padded = np.pad(img, pad_size, mode="reflect")
    # Extract sliding windows of shape (kernel_size, kernel_size)
    windows = sliding_window_view(padded, (kernel_size, kernel_size))
    # Convolve by taking the sum of elementwise products
    smoothed = np.sum(windows * kernel, axis=(-1, -2))
    return smoothed
