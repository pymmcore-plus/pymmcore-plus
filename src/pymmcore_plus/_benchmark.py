import timeit

from pymmcore import CMMCore


def benchmark_core(core: CMMCore, number: int = 1000) -> dict:
    """Take an initialized core with devices and benchmark various methods."""
    data: dict[str, float | str] = {}
    core.setExposure(1)
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
    for item in methods:
        if isinstance(item, tuple):
            meth, args = item
        else:
            meth, args = item, ()
        try:
            t = timeit.timeit(f"core.{meth}(*{args})", globals=locals(), number=number)
            data[meth] = round(1000 * t / number, 4)
        except Exception as e:
            data[meth] = str(e)

    return data


if __name__ == "__main__":
    from rich import print

    from pymmcore_plus.core._mmcore_plus import CMMCorePlus

    core = CMMCorePlus()
    core.loadSystemConfiguration()
    print(benchmark_core(core))
