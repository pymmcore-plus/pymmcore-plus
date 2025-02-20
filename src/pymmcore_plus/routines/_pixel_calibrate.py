from __future__ import annotations

import contextlib
import sys
import warnings
from typing import TYPE_CHECKING, Literal

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
    ) -> None:
        self.core = core
        self.roi = roi
        self.stage_device = stage_device
        self.camera_device = camera_device

        # last correlation matrix acquired, for debugging
        self.last_correlation: np.ndarray | None = None

        # pixel shifts for each stage move, accumulated during calibration
        # mapping of {(dx_stage, dy_stage): (dx_pixel, dy_pixel)}
        self._pixel_shifts: dict[tuple[float, float], tuple[float, float]] = {}

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

    def _default_moves(self) -> list[tuple[float, float]]:
        dist = self._max_distance / 2
        # Generate moves along each axis, and along the diagonal.
        steps = np.linspace(-dist, dist, self._num_steps)
        x_moves = [(float(i), 0) for i in steps]
        y_moves = [(0, float(i)) for i in steps]
        xy_moves = [(float(i), float(i)) for i in steps]
        return x_moves + y_moves + xy_moves

    def calibrate(self, moves: list[tuple[float, float]] | None = None) -> np.ndarray:
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
            moves = self._default_moves()

        # For each known stage move, capture a new image and measure pixel displacement.
        self._pixel_shifts.clear()
        for dx_stage, dy_stage in moves:
            new_stage = (x_initial + dx_stage, y_initial + dy_stage)
            self._move_to(*new_stage)
            img = self._capture_roi()
            pixel_shifts, self.last_correlation = measure_image_displacement(
                ref, img, window=self._window, subpixel_method=self._subpixel_method
            )
            self._pixel_shifts[(dx_stage, dy_stage)] = pixel_shifts
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
        return affine

    def affine(self) -> np.ndarray:
        """Returns the current affine transform.

        The value is cached after the first call, and is cleared whenever a new pixel
        shift is acquired during calibration.
        """
        # Solve for the pure linear transformation A (a 2x2 matrix) that maps pixel
        # shifts to stage shifts. That is, we want: stage_shifts @ A = pixel_shifts
        if self._cached_affine is None:
            if not self._pixel_shifts:  # pragma: no cover
                raise RuntimeError(
                    "No pixel shifts have been recorded. Run calibrate() first."
                )
            stage_shifts, pixel_shifts = zip(*self._pixel_shifts.items())
            A = np.linalg.lstsq(np.array(stage_shifts), np.array(pixel_shifts))[0]
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

    def pixel_size(self) -> float:
        """Returns the pixel size in microns."""
        return float(np.linalg.norm(self.affine()[0, 0:2]))

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

    # Find the peak location and calculate the shift.
    peak_idx = np.unravel_index(np.argmax(correlation), correlation.shape)
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
    return (shift[1] + sub_x, shift[0] + sub_y), correlation


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


def affine(
    shifts: Mapping[tuple[float, float], tuple[float, float]],
    robust: bool = False,
    method: Literal["iterative", "ransac"] = "iterative",
) -> np.ndarray:
    stage_shifts, pixel_shifts = zip(*shifts.items())
    stage_shifts = np.array(stage_shifts)
    pixel_shifts = np.array(pixel_shifts)

    if robust:
        if method == "iterative":
            A = robust_affine(stage_shifts, pixel_shifts, threshold=1.0)
        elif method == "ransac":
            A = ransac_affine(stage_shifts, pixel_shifts, threshold=1.0, iterations=100)
        else:
            raise ValueError("Invalid robust method.")
    else:
        A = np.linalg.lstsq(stage_shifts, pixel_shifts, rcond=None)[0]

    if np.linalg.det(A) == 0:
        warnings.warn(
            "Singular matrix detected. Affine transform may be invalid.", stacklevel=2
        )

    affine = np.eye(3, dtype=np.float32)
    affine[:2, :2] = A
    return affine


def robust_affine(
    stage_shifts: np.ndarray, pixel_shifts: np.ndarray, threshold: float = 1.0
) -> np.ndarray:
    # Initial least squares solution
    A = np.linalg.lstsq(stage_shifts, pixel_shifts, rcond=None)[0]

    # Compute residuals for each correspondence
    predictions = stage_shifts @ A
    residuals = np.linalg.norm(predictions - pixel_shifts, axis=1)
    median_residual = np.median(residuals)

    # Identify inliers
    inliers = residuals < threshold * median_residual
    if np.sum(inliers) < 2:
        raise RuntimeError("Too few inliers for robust estimation.")

    # Recompute using inliers only
    A_robust = np.linalg.lstsq(
        stage_shifts[inliers], pixel_shifts[inliers], rcond=None
    )[0]
    return A_robust


def ransac_affine(
    stage_shifts: np.ndarray,
    pixel_shifts: np.ndarray,
    threshold: float = 1.0,
    iterations: int = 100,
) -> np.ndarray:
    import random

    best_inliers = []
    best_A = None

    n = stage_shifts.shape[0]
    for _ in range(iterations):
        # Randomly sample 2 correspondences (minimal for 2x2)
        indices = random.sample(range(n), 2)
        subset_stage = stage_shifts[indices]
        subset_pixel = pixel_shifts[indices]
        # Compute affine transform for the subset
        try:
            A_candidate = np.linalg.lstsq(subset_stage, subset_pixel, rcond=None)[0]
        except np.linalg.LinAlgError:
            continue

        # Compute residuals for all correspondences
        predictions = stage_shifts @ A_candidate
        residuals = np.linalg.norm(predictions - pixel_shifts, axis=1)
        inliers = residuals < threshold

        # If this model has more inliers than previous ones, update best model.
        if np.sum(inliers) > np.sum(best_inliers):
            best_inliers = inliers
            best_A = A_candidate

    if best_A is None or np.sum(best_inliers) < 2:
        raise RuntimeError("RANSAC failed to find a robust affine transformation.")

    # Recompute the affine transform using all inliers from the best model.
    A_robust = np.linalg.lstsq(
        stage_shifts[best_inliers], pixel_shifts[best_inliers], rcond=None
    )[0]
    return A_robust
