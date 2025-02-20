from contextlib import suppress
from typing import Iterable

import numpy as np

from pymmcore_plus.core._mmcore_plus import CMMCorePlus
from pymmcore_plus.routines import AutoCameraCalibrator
from pymmcore_widgets import ImagePreview, SnapButton

from qtpy.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class GUI(QWidget):
    def __init__(self) -> None:
        super().__init__()

        preview = ImagePreview(mmcore=core)
        snap = SnapButton(mmcore=core)

        self.run_btn = QPushButton("Run Calibration")
        # Create a Matplotlib figure and canvas
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax1 = self.figure.add_subplot(121)
        self.ax2 = self.figure.add_subplot(122)

        layout = QVBoxLayout(self)
        layout.addWidget(preview)
        layout.addWidget(self.canvas)
        layout.addWidget(snap)
        layout.addWidget(self.run_btn)

    def scatter(
        self, points: Iterable[tuple[tuple[float, float], tuple[float, float]]]
    ) -> None:
        self.ax1.clear()
        stage_shifts, pixel_shifts = zip(*points)
        self.ax1.scatter(*zip(*stage_shifts), label="Stage Shifts")
        self.ax1.scatter(*zip(*pixel_shifts), label="Pixel Shifts")
        self.ax1.legend()
        self.canvas.draw()

    def plot_correlation(self, image: np.ndarray) -> None:
        self.ax2.clear()
        self.ax2.imshow(image, cmap="gray", vmax=np.max(image)*1)
        self.canvas.draw()


app = QApplication([])

core = CMMCorePlus()
core.loadSystemConfiguration(r"c:\Users\Admin\dev\min.cfg")
calibrator = AutoCameraCalibrator(core)


@calibrator.calibration_complete.connect
def _on_calibration_complete() -> None:
    print("Calibration complete")
    print("affine:", calibrator.affine())
    print("pixel size:", calibrator.pixel_size())
    print("rotation:", calibrator.rotation())


gui = GUI()
gui.show()
gui.run_btn.clicked.connect(lambda: calibrator.calibrate())


@calibrator.shift_acquired.connect
def _on_shift_acquired() -> None:
    print("---------")
    print("Shift acquired")
    print("pixel size:", calibrator.pixel_size(False), calibrator.pixel_size(True))
    print("rotation:", calibrator.rotation())
    print("rotation:", calibrator.affine())

    gui.scatter(calibrator.pixel_shifts())
    gui.plot_correlation(calibrator.last_correlation)
    QApplication.processEvents()


# app.exec()
