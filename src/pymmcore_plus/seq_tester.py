from dataclasses import dataclass
from typing import Any, Self

import numpy as np


@dataclass
class CameraInfo:
    name: str
    serial_img_num: int
    is_sequence: bool
    cumulative_img_num: int
    frame_num: int

    @classmethod
    def validate(cls, val: Any) -> "CameraInfo":
        if isinstance(val, cls):
            return val
        if isinstance(val, dict):
            return cls(**val)
        if isinstance(val, (list, tuple)):
            return cls(*val)
        raise TypeError(f"Cannot convert {val} to CameraInfo")


@dataclass
class Setting:
    device: str
    property: str
    type_: type
    value: Any

    @classmethod
    def validate(cls, val: Any) -> Self:
        if isinstance(val, cls):
            return val
        if isinstance(val, dict):
            return cls(**val)
        if isinstance(val, list):
            return cls.from_list(val)
        raise TypeError(f"Cannot convert {val} to Setting")

    @classmethod
    def from_list(cls, val: list) -> Self:
        (dev, prop), (typ, val) = val
        return cls(dev, prop, typ, val)


@dataclass
class SettingEvent(Setting):
    count: int

    @classmethod
    def from_list(cls, val: list) -> Self:
        (dev, prop), (typ, val), count = val
        return cls(dev, prop, typ, val, count)


@dataclass
class InfoPacket:
    hub_global_packet_nr: int
    camera: CameraInfo
    start_counter: int
    current_counter: int
    start_state: list[Setting]
    current_state: list[Setting]
    history: list[SettingEvent]

    def __post_init__(self) -> None:
        self.camera = CameraInfo.validate(self.camera)
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
