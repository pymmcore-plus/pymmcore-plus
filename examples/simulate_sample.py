# /// script
# dependencies = [
#     "pymmcore-plus[simulate]",
#     "pymmcore-widgets[PyQt6]",
# ]
#
# [tool.uv.sources]
# pymmcore-plus = { path = "../", editable = true }
# ///
"""Example: Simulated microscope sample with Qt widgets.

This example demonstrates the experimental simulate module with interactive
Qt widgets for controlling the microscope state (stage position, properties, etc.).

Run with: uv run examples/simulate_sample.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pymmcore_widgets import (
    ImagePreview,
    LiveButton,
    PropertyBrowser,
    SnapButton,
    StageWidget,
)
from qtpy.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.experimental.simulate import (
    Line,
    Point,
    Rectangle,
    RenderConfig,
    Sample,
)

if TYPE_CHECKING:
    from qtpy.QtGui import QPixmap


class SimulationWidget(QWidget):
    """Widget for displaying simulated microscope images."""

    def __init__(self, core: CMMCorePlus) -> None:
        super().__init__()

        self.core = core
        self._pixmap: QPixmap | None = None

        # Image display
        self.image_viewer = ImagePreview(mmcore=core)

        # Snap button
        self.snap_button = SnapButton(mmcore=core)
        self.live_button = LiveButton(mmcore=core)

        # Stage widgets
        self.stage_widget = StageWidget("XY", mmcore=core)
        self.stage_widget.snap_checkbox.setChecked(True)
        self.z_widget = StageWidget("Z", mmcore=core)
        self.z_widget.snap_checkbox.setChecked(True)

        # Property browser (separate window)
        self.props = PropertyBrowser(mmcore=core)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.image_viewer)

        btns = QHBoxLayout()
        btns.addWidget(self.snap_button)
        btns.addWidget(self.live_button)
        layout.addLayout(btns)

        stages = QHBoxLayout()
        stages.addWidget(self.stage_widget)
        stages.addWidget(self.z_widget)
        layout.addLayout(stages)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.props)
        main_layout.addLayout(layout)


def create_sample(
    n_lines: int = 400,
    n_points: int = 200,
    n_rectangles: int = 30,
    extent: int = 1000,
    seed: int = 42,
) -> Sample:
    """Create a sample with random objects."""
    rng = np.random.default_rng(seed)

    objects: list = []

    def rnd_coords() -> tuple[int, int]:
        return (int(rng.integers(-extent, extent)), int(rng.integers(-extent, extent)))

    # Random lines
    objects.extend(
        Line(start=rnd_coords(), end=rnd_coords(), intensity=int(rng.integers(50, 150)))
        for _ in range(n_lines)
    )

    # Random points
    objects.extend(
        Point(
            *rnd_coords(),
            intensity=int(rng.integers(30, 150)),
            radius=float(rng.uniform(2, 12)),
        )
        for _ in range(n_points)
    )

    # Some rectangles
    objects.extend(
        Rectangle(
            top_left=rnd_coords(),
            width=float(rng.uniform(20, 60)),
            height=float(rng.uniform(20, 60)),
            intensity=int(rng.integers(20, 90)),
            fill=True,
        )
        for _ in range(n_rectangles)
    )

    config = RenderConfig(
        noise_std=3.0,
        shot_noise=True,
        defocus_scale=0.12,
        base_blur=1.5,
        backend="auto",
    )

    return Sample(objects, config)


if __name__ == "__main__":
    app = QApplication([])

    core = CMMCorePlus()
    core.loadSystemConfiguration()

    window = SimulationWidget(core)
    window.setWindowTitle("Simulated Sample")
    window.resize(600, 1200)

    sample = create_sample()
    with sample.patch(core):
        core.snapImage()
        window.show()
        app.exec()
