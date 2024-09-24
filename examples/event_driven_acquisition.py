"""Simple simulator demonstrating event-driven acquisitions with pymmcore-plus."""

import random
import time
from queue import Queue

import numpy as np
from useq import MDAEvent

from pymmcore_plus import CMMCorePlus


class Analyzer:
    """Analyzes images and returns a dict of results."""

    def run(self, data) -> dict:
        # Fake analysis; randomly return a dict with a value of None 10% of the time
        if random.random() < 0.1:
            return {"result": "STOP"}
        else:
            return {"result": random.random()}


class Controller:
    STOP_EVENT = object()

    def __init__(self, analyzer: Analyzer, mmc: CMMCorePlus, queue: Queue):
        self._analyzer = analyzer  # analyzer of images
        self._queue = queue  # queue of MDAEvents
        self._results: dict = {}  # results of analysis

        self._mmc = mmc
        mmc.mda.events.frameReady.connect(self._on_frame_ready)

    def _on_frame_ready(self, img: np.ndarray, event: MDAEvent) -> None:
        # Analyze the image
        self._results = self._analyzer.run(img)

    def run(self) -> None:
        # convert the queue to an iterable
        queue_sequence = iter(self._queue.get, self.STOP_EVENT)

        # Start the acquisition (run_mda is non-blocking)
        self._mmc.run_mda(queue_sequence)

        # Queue the first image acquisition
        self._queue.put(MDAEvent(exposure=10))

        # loop until the analyzer returns "STOP"
        while True:
            # get the last results from the analyzer
            result = self._results.pop("result", None)

            # Decide what to do. This is the key part of the reactive loop.
            if result == "STOP":
                # Do nothing and return
                print("Analyzer returned no results. Stopping...")
                self._queue.put(self.STOP_EVENT)
                break
            elif result:
                # Adjust the exposure time based on the results and continue
                print("Analyzer returned results. Continuing...")
                next_event = MDAEvent(exposure=10 * result)
                self._queue.put(next_event)
            else:
                # No results yet, wait a bit and check again
                time.sleep(0.1)


def main():
    # Setup the MM Core
    mmc = CMMCorePlus()
    mmc.loadSystemConfiguration()

    # create the Queue that will hold the MDAEvents
    q = Queue()

    # Setup the controller and analyzer
    analyzer = Analyzer()
    controller = Controller(analyzer, mmc, q)

    # Start the acquisition
    controller.run()


if __name__ == "__main__":
    main()
