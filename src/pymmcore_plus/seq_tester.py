"""Classes for working with SequenceTester devices.

SequenceTester is a Micro-Manager device that encodes information about the state
of the system into the image data. This module provides a class for decoding that
information.

Decoding images requires the `msgpack` package to be installed.
A typical way to setup the device would be:

```python
core = CMMCorePlus()
core.loadDevice("THub", "SequenceTester", "THub")
core.initializeDevice("THub")
core.loadDevice("TCamera", "SequenceTester", "TCamera")
core.setParentLabel("TCamera", "THub")
core.setProperty("TCamera", "ImageMode", "MachineReadable")
core.setProperty("TCamera", "ImageWidth", 128)
core.setProperty("TCamera", "ImageHeight", 128)
core.initializeDevice("TCamera")
core.setCameraDevice("TCamera")
```

Then, to decode an image:

```python
from pymmcore_plus.seq_tester import decode_image

core.snapImage()
info = decode_image(core.getImage())
```
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import builtins

    import numpy as np
    from typing_extensions import Self  # py311

__all__ = ["CameraInfo", "InfoPacket", "Setting", "SettingEvent", "decode_image"]


@dataclass
class CameraInfo:
    """Information about a SequenceTester camera."""

    name: str
    serial_img_num: int
    is_sequence: bool
    cumulative_img_num: int
    frame_num: int

    @classmethod
    def validate(cls, val: Any) -> CameraInfo:
        """Coerce val into CameraInfo object."""
        if isinstance(val, cls):
            return val
        if isinstance(val, dict):
            return cls(**val)
        if isinstance(val, (list, tuple)):
            return cls(*val)
        raise TypeError(f"Cannot convert {val} to CameraInfo")


@dataclass
class Setting:
    """Setting of a SequenceTester property."""

    device: str
    property: str
    type: builtins.type
    value: Any

    @classmethod
    def validate(cls, val: Any) -> Self:
        """Coerce val into Setting object."""
        if isinstance(val, cls):
            return val
        if isinstance(val, dict):
            return cls(**val)
        if isinstance(val, list):
            return cls._from_list(val)
        raise TypeError(f"Cannot convert {val} to Setting")

    @classmethod
    def _from_list(cls, val: list) -> Self:
        (dev, prop), (type_, val) = val
        return cls(dev, prop, type_, val)


@dataclass
class SettingEvent(Setting):
    """Historical Setting."""

    count: int

    @classmethod
    def _from_list(cls, val: list) -> Self:
        (dev, prop), (type_, val), count = val
        return cls(dev, prop, type_, val, count)


@dataclass
class InfoPacket:
    """Data produced by a SequenceTester camera."""

    hub_global_packet_nr: int
    camera_info: CameraInfo
    start_counter: int
    current_counter: int
    start_state: list[Setting]
    current_state: list[Setting]
    history: list[SettingEvent]

    def __post_init__(self) -> None:
        """Validate all fields."""
        self.camera_info = CameraInfo.validate(self.camera_info)
        self.start_state = [Setting.validate(s) for s in self.start_state]
        self.current_state = [Setting.validate(s) for s in self.current_state]
        self.history = [SettingEvent.validate(h) for h in self.history]


def decode_image(img: np.ndarray) -> InfoPacket:
    """Extract data produced by a SequenceTester camera."""
    try:
        import msgpack
    except ImportError as e:
        raise ImportError(
            "msgpack is required to decode image metadata from SequenceTester. "
            "Try `pip install msgpack`."
        ) from e

    unpacker = msgpack.Unpacker()
    unpacker.feed(img.ravel())
    return InfoPacket(*next(unpacker))
