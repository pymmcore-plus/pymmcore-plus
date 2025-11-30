# /// script
# dependencies = [
#     "pymmcore-plus[simulate]",
#     "pymmcore-widgets[PyQt6]",
# ]
#
# [tool.uv.sources]
# pymmcore-plus = { path = "../" }
# ///
"""Example: Simulated microscope sample with Qt widgets.

This example demonstrates the experimental simulate module with interactive
Qt widgets for controlling the microscope state (stage position, properties, etc.).

Run with: uv run examples/simulate_sample.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageQt
from pymmcore_widgets import LiveButton, PropertyBrowser, SnapButton, StageWidget
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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

    def __init__(self, core: CMMCorePlus, sample: Sample) -> None:
        super().__init__()

        self.core = core
        self.sample = sample
        self._pixmap: QPixmap | None = None

        # Image display
        self.image_label = QLabel()
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Snap button
        self.snap_button = SnapButton()
        self.live_button = LiveButton()

        # Stage widgets
        self.stage_widget = StageWidget("XY")
        self.stage_widget.snap_checkbox.setChecked(True)
        self.z_widget = StageWidget("Z")
        self.z_widget.snap_checkbox.setChecked(True)

        # Property browser (separate window)
        self.props = PropertyBrowser(mmcore=core)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.image_label)

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

        # Connect to snap event
        self.core.events.imageSnapped.connect(self._on_snap)

    def _on_snap(self) -> None:
        """Handle snap event - render and display the simulated image."""
        # Render the sample at current state
        img = self.sample.render()
        self._pixmap = ImageQt.toqpixmap(Image.fromarray(img))
        self._update_display()

    def _update_display(self) -> None:
        """Update the displayed image, scaling to fit."""
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, a0: Any) -> None:
        """Re-scale image on resize."""
        self._update_display()
        super().resizeEvent(a0)


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

    # Random lines
    objects.extend(
        Line(
            start=(
                int(rng.integers(-extent, extent)),
                int(rng.integers(-extent, extent)),
            ),
            end=(
                int(rng.integers(-extent, extent)),
                int(rng.integers(-extent, extent)),
            ),
            intensity=int(rng.integers(20, 50)),
        )
        for _ in range(n_lines)
    )

    # Random points
    objects.extend(
        Point(
            x=int(rng.integers(-extent, extent)),
            y=int(rng.integers(-extent, extent)),
            intensity=int(rng.integers(30, 150)),
            radius=float(rng.uniform(2, 12)),
        )
        for _ in range(n_points)
    )

    # Some rectangles
    objects.extend(
        Rectangle(
            top_left=(
                int(rng.integers(-extent, extent)),
                int(rng.integers(-extent, extent)),
            ),
            width=float(rng.uniform(20, 60)),
            height=float(rng.uniform(20, 60)),
            intensity=int(rng.integers(40, 100)),
            fill=True,
        )
        for _ in range(n_rectangles)
    )

    config = RenderConfig(
        noise_std=3.0,
        shot_noise=True,
        defocus_scale=0.12,
        base_blur=1.5,
    )

    return Sample(objects, config)


if __name__ == "__main__":
    app = QApplication([])

    core = CMMCorePlus()
    core.loadSystemConfiguration()

    sample = create_sample()
    sample.patch(core)  # Set the core for rendering

    window = SimulationWidget(core, sample)
    window.setWindowTitle("Simulated Sample")
    window.resize(600, 700)

    # Initial snap
    core.snapImage()

    window.show()
    app.exec()
