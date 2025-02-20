import contextlib
import sys
import warnings
from typing import Optional

import numpy as np
from psygnal import Signal

from pymmcore_plus import CMMCorePlus


class CameraCalibrator:
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
        roi: Optional[tuple[int, int, int, int]] = None,
        # max distance should be no more than half the image size, to avoid FFT aliasing
        # the user can either enter this, or we could conceivably calculate it after the
        # first estimate of the pixel shift is calculated in `calibrate`.
        max_distance: int = 50,
        num_steps: int = 5,
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
            img = img[y : y + h, x : x + w]
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
            pixel_shifts, self.last_correlation = phase_correlate(ref, img)
            self._pixel_shifts[(dx_stage, dy_stage)] = pixel_shifts
            self.shift_acquired.emit()
            # clear this on each step in case a callback accesses .affine
            self._cached_affine = None

        # Return the affine transform that maps pixel shifts to stage shifts.
        affine = self.affine()
        # warn on high shear:
        if (shear := self.shear()) > 0.05:
            warnings.warn(
                f"High shear detected: {shear:.3f}. This may indicate a non-linear "
                "relationship between stage and pixel shifts.",
                stacklevel=2,
            )
        return affine

    def affine(self) -> np.ndarray:
        """Returns the current affine transform."""
        # Solve for the pure linear transformation A (a 2x2 matrix) that maps pixel
        # shifts to stage shifts. That is, we want: stage_positions @ A = pixel_shifts
        if self._cached_affine is None:
            if not self._pixel_shifts:  # pragma: no cover
                raise RuntimeError(
                    "No pixel shifts have been recorded. Run calibrate() first."
                )
            stage_positions, pixel_shifts = zip(*self._pixel_shifts.items())
            A = np.linalg.lstsq(np.array(stage_positions), np.array(pixel_shifts))[0]

            # Construct the full 2D affine transform. A is 2×2
            affine = np.eye(3, dtype=np.float32)
            affine[0, 0:2] = A[0]
            affine[1, 0:2] = A[1]
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


def phase_correlate(
    img1: np.ndarray, img2: np.ndarray
) -> tuple[tuple[float, float], np.ndarray]:
    """Estimates the translation shift between two images using phase correlation.

    Returns
    -------
    tuple[tuple[float, float], np.ndarray]
        The estimated shift in pixels (x, y) and the correlation matrix.
    """
    if not img1.shape == img2.shape:  # pragma: no cover
        raise ValueError("Input images must have the same shape.")

    # Compute FFTs of the two images.
    F1 = np.fft.fft2(img1)
    F2 = np.fft.fft2(img2)

    # Compute normalized cross-power spectrum.
    R = F1 * np.conjugate(F2)
    R /= np.abs(R) + sys.float_info.epsilon

    # Inverse FFT to get correlation; shift the zero-frequency component to center.
    corr = np.fft.ifft2(R)
    corr = np.fft.fftshift(corr)
    corr_abs = np.abs(corr)

    # Find the peak location.
    peak_idx = np.unravel_index(np.argmax(corr_abs), corr.shape)
    peak_y, peak_x, *_ = peak_idx
    center_y, center_x = np.array(corr.shape) // 2
    shift_y = peak_y - center_y
    shift_x = peak_x - center_x

    sub_y, sub_x = _parabolic_subpixel(corr_abs, (peak_y, peak_x))
    return (shift_x + sub_x, shift_y + sub_y), corr_abs


def _parabolic_subpixel(
    c: np.ndarray, peak: tuple[np.signedinteger, np.signedinteger]
) -> tuple[float, float]:
    """Subpixel refinement of a peak location in a 2D array."""
    py, px = peak
    sub_y, sub_x = 0.0, 0.0
    center_val = c[py, px]

    # Check if the peak is not on the border for x direction
    # Check if the peak is not on the border for x direction
    if 0 < px < c.shape[1] - 1:
        # Get the values to the left and right of the peak
        left = c[py, px - 1]
        right = c[py, px + 1]
        # Calculate the denominator for the parabolic fit
        denom = 2 * center_val - left - right
        # If the denominator is not zero, calculate the subpixel shift in x direction
        if denom != 0:
            sub_x = (left - right) / (2 * denom)

    # Check if the peak is not on the border for y direction
    if 0 < py < c.shape[0] - 1:
        top = c[py - 1, px]
        bottom = c[py + 1, px]
        denom = 2 * center_val - top - bottom
        if denom != 0:
            sub_y = (top - bottom) / (2 * denom)

    return sub_y, sub_x
