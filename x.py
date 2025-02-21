import numpy as np
from PIL import ImageQt
from pymmcore_widgets import PropertyBrowser, SnapButton, StageWidget
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QHBoxLayout, QWidget

from pymmcore_plus.core._mmcore_plus import CMMCorePlus
from pymmcore_plus.simulation.sample_render import Line, Point, RenderEngine


class Simulation(QWidget):
    def __init__(self, core: CMMCorePlus) -> None:
        super().__init__()

        self.core = core
        self.image = QLabel()
        self.image.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.snap_button = SnapButton()
        self.core.events.imageSnapped.connect(self.snap_image)
        self.stage_widget = StageWidget("XY")
        self.stage_widget.snap_checkbox.setChecked(True)
        self.z_widget = StageWidget("Z")
        self.z_widget.snap_checkbox.setChecked(True)
        self.props = PropertyBrowser(mmcore=core)
        self.props.show()
        layout = QVBoxLayout(self)
        layout.addWidget(self.image)
        layout.addWidget(self.snap_button)
        stages = QHBoxLayout()
        stages.addWidget(self.stage_widget)
        stages.addWidget(self.z_widget)
        layout.addLayout(stages)

    def snap_image(self) -> None:
        state = core.state()
        img = engine.render(state)
        # Convert the Pillow image to a QPixmap.
        self._pixmap = ImageQt.toqpixmap(img)
        self.update_image()

    def update_image(self) -> None:
        if self._pixmap is None:
            return
        # Scale the pixmap to the size of the QLabel, preserving aspect ratio,
        # using nearest neighbor interpolation.
        scaled_pixmap = self._pixmap.scaled(
            self.image.size(),  # target size
            Qt.AspectRatioMode.KeepAspectRatio,  # keep the original aspect ratio
            Qt.TransformationMode.FastTransformation,  # nearest neighbor interpolation
        )
        self.image.setPixmap(scaled_pixmap)

    def resizeEvent(self, event) -> None:
        # Re-scale the image whenever the widget is resized.
        self.update_image()
        super().resizeEvent(event)


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    core = CMMCorePlus()
    core.loadSystemConfiguration()

    # Create some sample objects in continuous space (e.g., microns)
    # sample_objects = [
    #     Bitmap((-128, -128), np.random.randint(0, 255, (256, 256)).astype(np.uint8)),
    #     Point(10, 10, radius=3),
    #     Point(100, 100, radius=3),
    #     RegularPolygon((-100, -30, 50), 7, rotation=38, outline=(255, 0, 0)),
    #     Point(110, 100, radius=1),
    #     Line((10, -10), (100, -100)),
    #     Polygon([(-50, -50), (37, 12), (112, 10), (59, 100)]),
    #     Arc((50, 50, 100, 100), -20, 30),
    #     Ellipse((150, 150), 200, 100),
    #     Rectangle((80, 120), 40, 30, radius=5),
    # ]
    # draw 200 randomly oriented lines and points
    sample_objects = [
        Line(
            (np.random.randint(-800, 800), np.random.randint(-800, 800)),
            (np.random.randint(-800, 800), np.random.randint(-800, 800)),
            color=30,
        )
        for _ in range(400)
    ]
    sample_objects += [
        Point(
            np.random.randint(-1000, 1000),
            np.random.randint(-1000, 1000),
            radius=np.random.randint(1, 12),
            color=15,
        )
        for _ in range(200)
    ]

    engine = RenderEngine(sample_objects)

    app = QApplication([])
    window = Simulation(core)
    core.snapImage()
    window.show()
    app.exec()
