import numpy as np
from PIL import ImageQt
from pymmcore_widgets import SnapButton, StageWidget
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from pymmcore_plus.core._mmcore_plus import CMMCorePlus
from pymmcore_plus.simulation.sample_render import (
    Arc,
    Bitmap,
    Ellipse,
    Line,
    Point,
    Polygon,
    Rectangle,
    RegularPolygon,
    RenderEngine,
)


class Simulation(QWidget):
    def __init__(self, core: CMMCorePlus) -> None:
        super().__init__()

        self.core = core
        self.image = QLabel()
        self.snap_button = SnapButton()
        self.core.events.imageSnapped.connect(self.snap_image)
        self.stage_widget = StageWidget("XY")
        self.stage_widget.snap_checkbox.setChecked(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.image)
        layout.addWidget(self.snap_button)
        layout.addWidget(self.stage_widget)

    def snap_image(self) -> None:
        state = core.state()
        img = engine.render(state)
        self.image.setPixmap(ImageQt.toqpixmap(img))


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    core = CMMCorePlus()
    core.loadSystemConfiguration()

    # Create some sample objects in continuous space (e.g., microns)
    sample_objects = [
        Bitmap((0, 0), np.random.randint(0, 255, (100, 100)).astype(np.uint8)),
        Point(10, 10, radius=3),
        Point(100, 100, radius=3),
        RegularPolygon((-100, -30, 50), 7, rotation=38, outline=(255, 0, 0)),
        Point(110, 100, radius=1),
        Line((10, -10), (100, -100)),
        Polygon([(-50, -50), (37, 12), (112, 10), (59, 100)]),
        Arc((50, 50, 100, 100), -20, 30),
        Ellipse((150, 150), 200, 100),
        Rectangle((80, 120), 40, 30, radius=5),
    ]
    engine = RenderEngine(sample_objects)

    app = QApplication([])
    window = Simulation(core)
    window.show()
    app.exec()
