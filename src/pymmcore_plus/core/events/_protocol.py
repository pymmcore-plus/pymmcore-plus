from __future__ import annotations

from typing import (
    Any,
    Callable,
    ClassVar,
    Protocol,
    overload,
    runtime_checkable,
)

from typing_extensions import Self


@runtime_checkable
class PSignalInstance(Protocol):
    """The protocol that a signal instance must implement.

    In practice this will either be a `pyqtSignal/pyqtBoundSignal` or a
    `psygnal.SignalInstance`.
    """

    def connect(self, slot: Callable) -> Any:
        """Connect slot to this signal."""

    def disconnect(self, slot: Callable | None = None) -> Any:
        """Disconnect slot from this signal.

        If `None`, all slots should be disconnected.
        """

    def emit(self, *args: Any) -> Any:
        """Emits the signal with the given arguments."""


@runtime_checkable
class PSignal(Protocol):
    """Descriptor that returns a signal instance."""

    @overload
    def __get__(self, instance: None, owner: type, /) -> Self: ...
    @overload
    def __get__(self, instance: Any, owner: type | None = None, /) -> Any: ...
    def __get__(
        self, instance: Any, owner: type | None = ..., /
    ) -> PSignalInstance | PSignal:
        """Returns the signal instance for this descriptor."""
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


    core.events.exposureChanged.connect(my_callback)
    ```

    Events may also be connected as a decorator:

    ```python
    @core.events.exposureChanged.connect
    def on_exposure_changed(device: str, new_exposure: float): ...
    ```

    ------
    """

    # native MMCore callback events
    propertiesChanged: ClassVar[PSignal]
    """Emits with no arguments when properties have changed."""
    propertyChanged: ClassVar[PSignal]
    """Emits `(name: str, propName: str, propValue: str)` when a specific property has changed."""  # noqa: E501
    channelGroupChanged: ClassVar[PSignal]
    """Emits `(newChannelGroupName: str)` when a channel group has changed."""
    configGroupChanged: ClassVar[PSignal]
    """Emits `(groupName: str, newConfigName: str)` when a config group has changed."""
    systemConfigurationLoaded: ClassVar[PSignal]
    """Emits with no arguments when the system configuration has been loaded."""
    pixelSizeChanged: ClassVar[PSignal]
    """Emits `(newPixelSizeUm: float)` when the pixel size has changed."""
    pixelSizeAffineChanged: ClassVar[PSignal]
    """Emits `(float, float, float, float, float, float)` when the pixel size affine has changed."""  # noqa: E501
    stagePositionChanged: ClassVar[PSignal]
    """Emits `(name: str, pos: float)` when a stage position has changed."""
    XYStagePositionChanged: ClassVar[PSignal]
    """Emits `(name: str, xpos: float, ypos: float)` when an XY stage position has changed."""  # noqa: E501
    xYStagePositionChanged: ClassVar[PSignal]  # alias
    exposureChanged: ClassVar[PSignal]
    """Emits `(name: str, newExposure: float)` when an exposure has changed."""
    SLMExposureChanged: ClassVar[PSignal]
    """Emits `(name: str, newExposure: float)` when the exposure of the SLM device changes."""  # noqa: E501
    sLMExposureChanged: ClassVar[PSignal]  # alias

    # added for CMMCorePlus
    configSet: ClassVar[PSignal]
    """Emits `(str, str)` when a config has been set.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    imageSnapped: ClassVar[PSignal]
    """Emits with no arguments whenever snap is called.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    mdaEngineRegistered: ClassVar[PSignal]
    """Emits `(MDAEngine, MDAEngine)` when an MDAEngine is registered.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """

    continuousSequenceAcquisitionStarting: ClassVar[PSignal]
    """Emits with no arguments *before* continuous sequence acquisition is started.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    continuousSequenceAcquisitionStarted: ClassVar[PSignal]
    """Emits with no arguments *after* continuous sequence acquisition has started.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    sequenceAcquisitionStarting: ClassVar[PSignal]
    """Emits `(str,)` *before* sequence acquisition is started.

    !!! critical "Breaking Change"
        In `pymmcore-plus` version 0.16.0, the `sequenceAcquisitionStarting` signal
        was *reduced* from `(str, int, float, bool)` to `(str,)` to match the signature
        emitted by the C++ MMCore library.

    `(cameraLabel,)`
    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    sequenceAcquisitionStarted: ClassVar[PSignal]
    """Emits `(str)` *after* sequence acquisition has started.

    !!! critical "Breaking Change"
        In `pymmcore-plus` version 0.16.0, the `sequenceAcquisitionStarted` signal
        was *reduced* from `(str, int, float, bool)` to `(str,)` to match the signature
        emitted by the C++ MMCore library.

    (cameraLabel,)
    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    sequenceAcquisitionStopped: ClassVar[PSignal]
    """Emits `(str)` when sequence acquisition is stopped.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    autoShutterSet: ClassVar[PSignal]
    """Emits `(bool)` when the auto shutter setting is changed.

    """
    configGroupDeleted: ClassVar[PSignal]
    """Emits `(str)` when a config group is deleted.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    configDeleted: ClassVar[PSignal]
    """Emits `(str, str)` when a config is deleted.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    configDefined: ClassVar[PSignal]
    """Emits `(str, str, str, str, str)` when a config is defined.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """
    roiSet: ClassVar[PSignal]
    """Emits `(str, int, int, int, int)` when an ROI is set.

    > :sparkles: This signal is unique to `pymmcore-plus`.
    """

    def devicePropertyChanged(
        self, device: str, property: str | None = None
    ) -> PSignalInstance:
        """Return object to connect/disconnect to device/property-specific changes.

        Note that the callback provided to `.connect()` must take *two* parameters
        (property_name, new_value) if only `device` is provided, and *one* parameter
        (new_value) of both `device` and `property` are provided.

        Parameters
        ----------
        device : str
            A device label
        property : Optional[str]
            Optional property label.  If not provided, all property changes on `device`
            will trigger an event emission. by default None

        Returns
        -------
        _PropertySignal
            Object with `connect` and `disconnect` methods that attach a callback to
            the change event of a specific property or device.

        Examples
        --------
        >>> core.events.devicePropertyChanged("Camera", "Gain").connect(callback)
        >>> core.events.devicePropertyChanged("Camera").connect(callback)
        """
