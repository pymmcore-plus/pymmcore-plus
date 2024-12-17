import timeit

from pymmcore_plus import CMMCorePlus, DeviceType


class Benchmark:
    device_type = DeviceType.Camera

    def __init__(self, core: CMMCorePlus, label: str) -> None:
        self.core = core
        self.label = label

    def setup(self) -> None:
        pass

    def run(self, number: int) -> dict[str, float | str]:
        data: dict[str, float | str] = {}

        # get methods in the order of definition, in reverse MRO order
        methods: list[str] = []
        for base in reversed(type(self).mro()):
            methods.extend(m for m in base.__dict__ if m.startswith("bench_"))

        for method_name in methods:
            try:
                t = timeit.timeit(getattr(self, method_name), number=number)
                result: float | str = round(1000 * t / number, 3)
            except Exception as e:
                result = str(e)
            data[method_name[6:]] = result
        return data


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


class StageBenchmark(Benchmark):
    device_type = DeviceType.Stage

    def setup(self) -> None:
        self.position = self.core.getPosition(self.label)

    def bench_getPosition(self) -> None:
        self.core.getPosition(self.label)

    def bench_setPosition(self) -> None:
        self.core.setPosition(self.label, self.position)


class CoreBenchmark(Benchmark):
    device_type = DeviceType.Core

    def bench_getDeviceAdapterNames(self) -> None:
        self.core.getDeviceAdapterNames()

    def bench_getLoadedDevices(self) -> None:
        self.core.getLoadedDevices()

    def bench_getSystemState(self) -> None:
        self.core.getSystemState()


def benchmark_core_and_devices(
    core: CMMCorePlus, number: int = 100
) -> dict[str, dict[str, float | str]]:
    """Take an initialized core with devices and benchmark various methods."""
    data: dict[str, dict[str, float | str]] = {}

    for cls in Benchmark.__subclasses__():
        if cls.device_type == DeviceType.Core:
            bench = cls(core, "Core")
            bench.setup()
            data["Core"] = bench.run(number)
        else:
            for dev in core.getLoadedDevicesOfType(cls.device_type):
                bench = cls(core, dev)
                bench.setup()
                data[dev] = bench.run(number)

    return data


def print_benchmarks(data: dict[str, dict[str, float | str]]) -> None:
    """Print the benchmark results in a human-readable format."""
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Benchmark results")
        table.add_column("Method", justify="right", style="green")
        table.add_column("Time (ms)", justify="right")
        for device, benches in data.items():
            table.add_row(f"Device: {device}", "------", style="yellow")
            for method, time in benches.items():
                if isinstance(time, float):
                    time = f"{time:.4f}"
                table.add_row(method, str(time))

        console = Console()
        console.print(table)
    except ImportError:
        print(data)


if __name__ == "__main__":
    import sys

    from rich import print

    from pymmcore_plus.core._mmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    if len(sys.argv) > 1 and (cfg := sys.argv[1]) != "demo":
        print("Loading system configuration from", sys.argv[1])
        core.loadSystemConfiguration(sys.argv[1])
    else:
        print("using demo configuration")
        core.loadSystemConfiguration()
    if len(sys.argv) > 2:
        number = int(sys.argv[2])
    else:
        number = 1000
    data = benchmark_core_and_devices(core, number)
    print_benchmarks(data)
