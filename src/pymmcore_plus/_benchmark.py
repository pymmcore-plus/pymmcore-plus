import timeit
import warnings
from collections.abc import Iterable

from pymmcore import CMMCore

try:
    from tqdm import tqdm
except ImportError:

    def tqdm(iterable: Iterable) -> Iterable:
        return iterable


def benchmark_core(core: CMMCore, number: int = 1000) -> dict:
    """Take an initialized core with devices and benchmark various methods."""
    data: dict[str, float | str] = {}
    methods: list[str | tuple[str, tuple]] = [
        "getDeviceAdapterNames",
        "getLoadedDevices",
        "getSystemState",
        "getCurrentPixelSizeConfig",
        "getAvailablePixelSizeConfigs",
        "getPixelSizeUm",
        "getPixelSizeAffine",
        "getMagnificationFactor",
    ]

    if cam := core.getCameraDevice():
        core.setExposure(1)
        if not (exp := core.getExposure()) == 1:
            warnings.warn(
                f"Exposure setting failed, real exposure: {exp}", stacklevel=2
            )
        methods.extend(
            [
                "getMultiROI",
                "getExposure",
                "snapImage",
                "getImage",
                "getImageWidth",
                "getImageHeight",
                "getImageBufferSize",
                "getImageBitDepth",
                "getNumberOfComponents",
                "getNumberOfCameraChannels",
                # "getAutoShutter",
                # "getShutterOpen",
                ("prepareSequenceAcquisition", (cam,)),
                # "getRemainingImageCount",
                # "getBufferTotalCapacity",
                # "getBufferFreeCapacity",
                # "isBufferOverflowed",
                # "getCircularBufferMemoryFootprint",
                # ("isExposureSequenceable", (cam,)),
                # ("getExposureSequenceMaxLength", (cam,)),
            ]
        )

    if xystage := core.getXYStageDevice():
        methods.extend(
            [
                "getXYPosition",
                "getXPosition",
                "getYPosition",
                ("setXYPosition", (xystage, *core.getXYPosition(xystage))),
                # ("home", (xystage,)),
                # ("stop", (xystage,)),
            ]
        )

    if zstage := core.getFocusDevice():
        methods.extend(
            [
                "getPosition",
                ("setPosition", (zstage, core.getPosition(zstage))),
            ]
        )

    if pxcfgs := core.getAvailablePixelSizeConfigs():
        methods.append(("getPixelSizeConfigData", (pxcfgs[0],)))
    for item in tqdm(methods):
        if isinstance(item, tuple):
            meth, args = item
        else:
            meth, args = item, ()
        try:
            t = timeit.timeit(f"core.{meth}(*{args})", globals=locals(), number=number)
            data[meth] = round(1000 * t / number, 3)
        except Exception as e:
            data[meth] = str(e)

    return data


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
    data = benchmark_core(core, number)

    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Benchmark results")
        table.add_column("Method", justify="right", style="green")
        table.add_column("Time (ms)", justify="right")
        for method, time in data.items():
            if isinstance(time, float):
                time = f"{time:.4f}"
            table.add_row(method, str(time))

        console = Console()
        console.print(table)
    except ImportError:
        print(data)
