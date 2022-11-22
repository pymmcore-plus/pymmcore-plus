from typing import Any, Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class PSignalInstance(Protocol):
    """The protocol that a signal instance must implement.

    In practice this will either be a `pyqtSignal/pyqtBoundSignal` or a
    `psygnal.SignalInstance`.
    """

    def connect(self, slot: Callable) -> Any:
        ...

    def disconnect(self, slot: Callable) -> Any:
        ...

    def emit(self, *args: Any) -> Any:
        ...


@runtime_checkable
class PCoreSignaler(Protocol):
    """Declares the protocol for all signals that will be emitted from CMMCorePlus.

    The main instance of this interface is available on the `CMMCorePlus` object at the
    [`events`][pymmcore_plus.CMMCorePlus.events] attribute. Each signal on `events` is
    an object has a `connect` and a `disconnect` method that you can use to
    connect/disconnect your own callback functions.  `connect` and `disconnect` accept a
    single argument, which is a callable that will be called when the signal is emitted.
    The callable should accept no more positional arguments than the signal emits (noted
    for each signal below), but may accept fewer.

    !!! note

        These events are a superset of those emitted by
        [MMEventCallback](https://valelab4.ucsf.edu/~MM/doc/mmcorej/mmcorej/MMEventCallback.html)
        in the MMCore C++ library.  The "on" prefix has been removed from the names
        here and the first letter lower cased.

        **Important**

        In the core C++ library (and in `pymmcore`), the emission of many of these
        events is left to the discretion of the device adapter.  In `pymmcore_plus`,
        we attempt to emit these events in a more consistent manner (e.g. by checking
        a particular value before and after calling into the C++ library).  So, the
        emission of these events is not guaranteed to be 1:1 with the C++ library;
        however, it should be easier to follow the state of the core when using
        `pymmcore_plus.CMMCorePlus`.

    Examples
    --------
    To connect to the `onExposureChanged` event emitted by MMCore, you
    would connect to the `exposureChanged` signal on this class:

    ```python
    from pymmcore_plus import CMMCorePlus

    core = CMMCorePlus()

    def on_exposure_changed(device: str, new_exposure: float):
        print(f"Exposure changed for {device} to {new_exposure}")

    core.exposureChanged.connect(my_callback)
    ```

    Events may also be connected as a decorator:

    ```python
    @core.exposureChanged.connect
    def on_exposure_changed(device: str, new_exposure: float):
        ...
    ```

    ------
    """

    # native MMCore callback events
    propertiesChanged: PSignalInstance
    """Emits with no arguments when properties have changed."""
    propertyChanged: PSignalInstance
    """Emits `(name: str, : propName: str, propValue: str)` when a specific property has changed."""  # noqa: E501
    channelGroupChanged: PSignalInstance
    """Emits `(newChannelGroupName: str)` when a channel group has changed."""
    configGroupChanged: PSignalInstance
    """Emits `(groupName: str, newConfigName: str)` when a config group has changed."""
    systemConfigurationLoaded: PSignalInstance
    """Emits with no arguments when the system configuration has been loaded."""
    pixelSizeChanged: PSignalInstance
    """Emits `(newPixelSizeUm: float)` when the pixel size has changed."""
    pixelSizeAffineChanged: PSignalInstance
    """Emits `(float, float, float, float, float, float)` when the pixel size affine has changed."""  # noqa: E501
    stagePositionChanged: PSignalInstance
    """Emits `(name: str, pos: float)` when a stage position has changed."""
    XYStagePositionChanged: PSignalInstance
    """Emits `(name: str, xpos: float, ypos: float)` when an XY stage position has changed."""  # noqa: E501
    xYStagePositionChanged: PSignalInstance  # alias
    exposureChanged: PSignalInstance
    """Emits `(name: str, newExposure: float)` when an exposure has changed."""
    SLMExposureChanged: PSignalInstance
    """Emits `(name: str, newExposure: float)` when the exposure of the SLM device changes."""  # noqa: E501
    sLMExposureChanged: PSignalInstance  # alias

    # added for CMMCorePlus
    configSet: PSignalInstance
    """Emits `(str, str)` when a config has been set.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    imageSnapped: PSignalInstance
    """Emits `(np.ndarray)` whenever snap is called.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    mdaEngineRegistered: PSignalInstance
    """Emits `(MDAEngine, MDAEngine)` when an MDAEngine is registered.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """

    continuousSequenceAcquisitionStarted: PSignalInstance
    """Emits with no arguments when continuous sequence acquisition is started.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    sequenceAcquisitionStarted: PSignalInstance
    """Emits `(str, int, float, bool)` when sequence acquisition is started.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    sequenceAcquisitionStopped: PSignalInstance
    """Emits `(str)` when sequence acquisition is stopped.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    autoShutterSet: PSignalInstance
    """Emits `(bool)` when the auto shutter setting is changed.

    """
    configGroupDeleted: PSignalInstance
    """Emits `(str)` when a config group is deleted.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    configDeleted: PSignalInstance
    """Emits `(str, str)` when a config is deleted.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    configDefined: PSignalInstance
    """Emits `(str, str, str, str, str)` when a config is defined.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    roiSet: PSignalInstance
    """Emits `(str, int, int, int, int)` when an ROI is set.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """

    def devicePropertyChanged(
        self, device: str, property: Optional[str] = None
    ) -> PSignalInstance:
        ...
