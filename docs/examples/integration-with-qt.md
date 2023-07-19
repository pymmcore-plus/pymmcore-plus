# Qt Integration

For a complex Qt application based on `pymmcore-plus` check out [napari-micromanager](https://github.com/pymmcore-plus/napari-micromanager#napari-micromanager) which implements a GUI to control microscopes.

`pymmcore-plus` is designed seamlessly integrate with Qt GUIs. It accomplishes this in two ways:

1. [`pymmcore_plus.CMMCorePlus.run_mda`][] runs in a thread in order to not block the event loop.
2. The `events` object will preferentially to use QSignals instead of of signals from the [psygnal](https://github.com/tlambert03/psygnal#psygnal) library. This helps keep things from crashing when working with callbacks in multiple threads.

This example requires qtpy and an Qt backend installed in the env:

```bash
pip install qtpy superqt Pyside2 # or pyqt5
```

## Avoiding blocking the Qt event loop

If you make a blocking call on the thread running the Qt event loop then your GUI will become
unresponsive. `pymmcore-plus` has two options to avoid this. The recommended way is to
use threads to call [`pymmcore_plus.CMMCorePlus.snapImage`][], and let pymmcore-plus handle the threading when you use
[`pymmcore_plus.CMMCorePlus.run_mda`][].

This example will use the recommended process-local(threads) approach.

The simple application will consist of a counter that increments so long as the event loop is not blocked, and two buttons to call the `snapImage` method. One button will call from a thread and the counter should continue, the other will blcok and will stop the counter.

**Key takeaways:**

1. Use `CMMCorePlus.instance()` to create the core object. This allows another script in the same process to use the same object.
2. Use a thread for blocking operations like `snapImage`.

```python
import sys

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from superqt.utils import create_worker

from pymmcore_plus import CMMCorePlus


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mmc = CMMCorePlus.instance()
        self.mmc.loadSystemConfiguration()
        self.mmc.setExposure(5000)  # 5 seconds

        self.counter = 0

        layout = QVBoxLayout()

        self.l = QLabel("Start")
        b_blocking = QPushButton("Snap blocking")
        b_threaded = QPushButton("Snap threaded")
        b_blocking.pressed.connect(self.snap_blocking)
        b_threaded.pressed.connect(self.snap_threaded)

        layout.addWidget(self.l)
        layout.addWidget(b_blocking)
        layout.addWidget(b_threaded)

        w = QWidget()
        w.setLayout(layout)
        self.setCentralWidget(w)
        self.show()

        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._recurring_timer)
        self.timer.start()

    def _recurring_timer(self):
        self.counter += 1
        self.l.setText("Counter: %d" % self.counter)

    def snap_threaded(self):
        # alternatively you could use the python threading module
        # or directly use QThreads
        create_worker(
            self._mmc.snapImage,
            _start_thread=True,
        )

    def snap_blocking(self):
        self.mmc.snapImage()



app = QApplication(sys.argv)
window = MainWindow()
app.exec_()
```
