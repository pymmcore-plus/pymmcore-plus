from matplotlib.colors import PowerNorm
import numpy as np
import useq
from pymmcore_plus.core._mmcore_plus import CMMCorePlus
from pymmcore_plus.routines import AutoCameraCalibrator
from pymmcore_widgets import ImagePreview, SnapButton

from qtpy.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from pymmcore_plus.routines._pixel_calibrate import *  # noqa
from pymmcore_plus.routines._pixel_calibrate import (
    _parabolic_subpixel,  # noqa
    _smooth_image,  # noqa
    _upsampled_subpixel,  # noqa
    _window,  # noqa
)


class GUI(QWidget):
    def __init__(self, core: CMMCorePlus, calibrator: AutoCameraCalibrator) -> None:
        super().__init__()
        self.calibrator = calibrator
        preview = ImagePreview(mmcore=core)
        snap = SnapButton(mmcore=core)

        self.run_btn = QPushButton("Run Calibration")
        self.run_btn.clicked.connect(self._calibrate)

        self.cancel_btn = QPushButton("Cancel Calibration")
        self.cancel_btn.clicked.connect(lambda: calibrator.cancel())

        # Create a Matplotlib figure and canvas
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.scatter_ax = self.figure.add_subplot(221)
        self.scatter_ax.axis("equal")
        self.cor_img = self.figure.add_subplot(222)
        self.cor_img.set_title("Correlation")
        self.rmse = self.figure.add_subplot(223)
        self.rmse.set_title("RMSE")
        self.pixel_estimate = self.figure.add_subplot(224)
        self.pixel_estimate.set_title("Pixel Estimates")
        self.rot_estimate = self.pixel_estimate.twinx()

        layout = QVBoxLayout(self)
        layout.addWidget(preview)
        layout.addWidget(self.canvas)
        layout.addWidget(snap)
        layout.addWidget(self.run_btn)
        layout.addWidget(self.cancel_btn)

        self._pixel_estimates = []
        self._rot_estimates = []
        self._rmses = []
        calibrator.shift_acquired.connect(self._on_shift_acquired)
        calibrator.calibration_started.connect(self._on_calibration_started)

    def _on_calibration_started(self) -> None:
        self._pixel_estimates = []
        self._rot_estimates = []
        self._rmses = []

    def _calibrate(self) -> None:
        step = 5
        grid = useq.GridRowsColumns(
            rows=5,
            columns=5,
            relative_to="center",
            fov_height=step,
            fov_width=step,
            mode="spiral",
        )

        moves = [(p.x, p.y) for p in grid]
        self.calibrator.calibrate(moves[1:])

    def _on_shift_acquired(self) -> None:
        # print("---------")
        # print("Shift acquired")
        # print("pixel size:", calibrator.pixel_size(False), calibrator.pixel_size(True))
        # print("rotation:", calibrator.rotation())
        # print("rotation:", calibrator.affine())
        c = self.calibrator
        c.affine()
        self.update_scatter()
        if (cor := c.last_correlation) is not None:
            self.plot_correlation(cor)
        self._pixel_estimates.append((c.pixel_size(False), c.pixel_size(True)))
        self._rot_estimates.append(c.rotation())
        self.plot_pixel_estimates()

        self._rmses.append(c.rmse)
        self.rmse.clear()
        self.rmse.plot(self._rmses)

        self.canvas.draw()
        QApplication.processEvents()

    def __del__(self) -> None:
        self.calibrator.cancel()

    def update_scatter(self) -> None:
        try:
            affine = self.calibrator.affine()[:2, :2]
        except:
            return

        self.scatter_ax.clear()
        stage_shifts, pixel_shifts = zip(*self.calibrator.pixel_shifts())
        # apply affine to pixel shifts
        pixel_shifts = (affine @ np.array(pixel_shifts).T).T

        # plot both sets of points as a scatter plot, with an arrow connecting paired
        # points
        self.scatter_ax.scatter(*zip(*stage_shifts), label="Stage Shifts")
        self.scatter_ax.scatter(*zip(*pixel_shifts), label="Pixel Shifts")
        for stage, pixel in zip(stage_shifts, pixel_shifts):
            self.scatter_ax.arrow(
                *stage, *(pixel - stage), head_width=0.1, head_length=0.1
            )
        self.scatter_ax.legend()
        self.scatter_ax.axis("equal")

    def plot_correlation(self, image: np.ndarray) -> None:
        self.cor_img.clear()
        height, width = image.shape
        extent = [-width / 2, width / 2, -height / 2, height / 2]
        self.cor_img.imshow(
            image,
            cmap="gray",
            norm=PowerNorm(0.5, vmax=np.max(image)),
            extent=extent,
            origin="upper",
        )

    def plot_pixel_estimates(self) -> None:
        self.pixel_estimate.clear()
        self.rot_estimate.clear()
        estimates = np.array(self._pixel_estimates)
        self.pixel_estimate.plot(estimates[:, 0], label="from vectors")
        self.pixel_estimate.plot(estimates[:, 1], label="from affine")
        self.rot_estimate.plot(self._rot_estimates, color="black", label="rotation")
        self.pixel_estimate.legend()


if not QApplication.instance():
    app = QApplication([])

core = CMMCorePlus().instance()
if not len(core.getLoadedDevices()) > 1:
    core.loadSystemConfiguration(r"c:\Users\Admin\dev\min.cfg")
calibrator = AutoCameraCalibrator(
    core, roi=(1024, 1024, 512, 512), subpixel_method="parabolic"
)


gui = GUI(core, calibrator)
gui.resize(1400, 1200)
gui.show()


# app.exec()
