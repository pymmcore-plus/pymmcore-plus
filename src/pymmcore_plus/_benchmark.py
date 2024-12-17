from __future__ import annotations

import timeit
import warnings
from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus, DeviceType

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from pymmcore_plus.core._device import Device


class Benchmark:
    device_type = DeviceType.Camera

    def __init__(self, core: CMMCorePlus, label: str = "") -> None:
        self.core = core
        self.label = label

    def setup(self) -> None:
        pass

    def device(self) -> Device | None:
        if self.label is not None:
            return self.core.getDeviceObject(self.label)
        return None

    def run(self, number: int) -> Iterator[tuple[str, float | str]]:
        # get methods in the order of definition, in reverse MRO order

        try:
            self.setup()
        except Exception as e:  # pragma: no cover
            warnings.warn(
                f"Setup failed on device {self.label!r}: {e}",
                RuntimeWarning,
                stacklevel=2,
            )
            return

        methods: list[str] = []
        for base in reversed(type(self).mro()):
            methods.extend(m for m in base.__dict__ if m.startswith("bench_"))

        for method_name in methods:
            try:
                t = timeit.timeit(getattr(self, method_name), number=number)
                result: float | str = round(1000 * t / number, 3)
            except Exception as e:
                result = str(e)
            yield method_name[6:], result


class CoreBenchmark(Benchmark):
    device_type = DeviceType.Core

    def bench_getDeviceAdapterNames(self) -> None:
        self.core.getDeviceAdapterNames()

    def bench_getLoadedDevices(self) -> None:
        self.core.getLoadedDevices()

    def bench_getSystemState(self) -> None:
        self.core.getSystemState()


class CameraBenchmark(Benchmark):
    device_type = DeviceType.Camera

    def setup(self) -> None:
        self.core.setCameraDevice(self.label)
        self.core.setExposure(self.label, 1)

    def bench_getMultiROI(self) -> None:
        self.core.getMultiROI()

    def bench_getExposure(self) -> None:
        self.core.getExposure(self.label)

    def bench_snapImage(self) -> None:
        self.core.snapImage()

    def bench_getImage(self) -> None:
        self.core.getImage()

    def bench_getImageWidth(self) -> None:
        self.core.getImageWidth()

    def bench_getImageHeight(self) -> None:
        self.core.getImageHeight()

    def bench_getImageBufferSize(self) -> None:
        self.core.getImageBufferSize()

    def bench_getImageBitDepth(self) -> None:
        self.core.getImageBitDepth()

    def bench_getNumberOfComponents(self) -> None:
        self.core.getNumberOfComponents()

    def bench_getNumberOfCameraChannels(self) -> None:
        self.core.getNumberOfCameraChannels()


class XYStageBenchmark(Benchmark):
    device_type = DeviceType.XYStage

    def setup(self) -> None:
        self.core.setXYStageDevice(self.label)
        self.position = self.core.getXYPosition(self.label)

    def bench_getXYPosition(self) -> None:
        self.core.getXYPosition(self.label)

    def bench_getXPosition(self) -> None:
        self.core.getXPosition(self.label)

    def bench_getYPosition(self) -> None:
        self.core.getYPosition(self.label)

    def bench_setXYPosition(self) -> None:
        self.core.setXYPosition(self.label, *self.position)

    def bench_setRelativeXYPosition(self) -> None:
        self.core.setRelativeXYPosition(self.label, 0, 0)

    def bench_isXYStageSequenceable(self) -> None:
        self.core.isXYStageSequenceable(self.label)


class StageBenchmark(Benchmark):
    device_type = DeviceType.Stage

    def setup(self) -> None:
        self.position = self.core.getPosition(self.label)

    def bench_getPosition(self) -> None:
        self.core.getPosition(self.label)

    def bench_setPosition(self) -> None:
        self.core.setPosition(self.label, self.position)

    def bench_setRelativePosition(self) -> None:
        self.core.setRelativePosition(self.label, 0)

    def bench_isStageSequenceable(self) -> None:
        self.core.isStageSequenceable(self.label)

    def bench_isStageLinearSequenceable(self) -> None:
        self.core.isStageLinearSequenceable(self.label)


class StateBenchmark(Benchmark):
    device_type = DeviceType.State

    def setup(self) -> None:
        self.initial_state = self.core.getState(self.label)
        try:
            self.labels: Sequence[str] = self.core.getStateLabels(self.label)
        except Exception:
            self.labels = []

    def bench_getState(self) -> None:
        self.core.getState(self.label)

    def bench_setState(self) -> None:
        self.core.setState(self.label, self.initial_state)

    def bench_getNumberOfStates(self) -> None:
        self.core.getNumberOfStates(self.label)

    def bench_getStateLabel(self) -> None:
        self.core.getStateLabel(self.label)

    def bench_getStateFromLabel(self) -> None:
        for label in self.labels:
            self.core.getStateFromLabel(self.label, label)


def benchmark_core_and_devices(
    core: CMMCorePlus, number: int = 100
) -> Iterable[Device | None | tuple[str, float | str]]:
    """Take an initialized core with devices and benchmark various methods.

    Yields
    ------
    Device | None | tuple[str, float | str]
        If a `Device`, it is the device object being benchmarked.
        If None, it is the core object being benchmarked.
        If a tuple, it is the method name and the time taken to run it.
    """
    for cls in Benchmark.__subclasses__():
        if cls.device_type == DeviceType.Core:
            bench = cls(core, "Core")
            yield bench.device()
            yield from bench.run(number)
        else:
            for dev in core.getLoadedDevicesOfType(cls.device_type):
                bench = cls(core, dev)
                yield bench.device()
                yield from bench.run(number)
