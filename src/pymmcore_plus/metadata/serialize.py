from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import timedelta
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import numpy as np

try:
    # use msgspec if available
    import msgspec
except ImportError:
    msgspec = None


if TYPE_CHECKING:
    import pydantic  # noqa: F401


def encode_hook(obj: Any, raises: bool = True) -> Any:
    """Hook to encode objects that are not JSON serializable."""
    if not TYPE_CHECKING:
        pydantic = sys.modules.get("pydantic")
    if pydantic and isinstance(obj, pydantic.BaseModel):
        try:
            return obj.model_dump(mode="json", exclude_unset=True)
        except (AttributeError, TypeError):
            return to_builtins(obj.dict(exclude_unset=True))
    if isinstance(obj, MappingProxyType):
        return dict(obj)
    if isinstance(obj, np.number):
        return obj.item()
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    if isinstance(obj, Enum):
        return obj.value
    if raises:
        raise NotImplementedError(f"Cannot serialize object of type {type(obj)}")
    return obj


# def decode_hook(type: type, obj: Any) -> Any:
#     """Hook to decode objects that are not JSON deserializable."""
#     if not TYPE_CHECKING:
#         pydantic = sys.modules.get("pydantic")
#     if pydantic:
#         with suppress(TypeError):
#             if issubclass(type, pydantic.BaseModel):
#                 return type.model_validate(obj)
#     raise NotImplementedError(f"Cannot deserialize object of type {type}")


def schema_hook(obj: type) -> dict[str, Any]:
    """Hook to convert objects to schema."""
    if not TYPE_CHECKING:
        pydantic = sys.modules.get("pydantic")
    if pydantic:
        with suppress(TypeError):
            if issubclass(obj, pydantic.BaseModel):
                return obj.model_json_schema()
    raise NotImplementedError(f"Cannot create schema for object of type {type(obj)}")


def msgspec_json_dumps(obj: Any, *, indent: int | None = None) -> bytes:
    """Serialize object to bytes."""
    encoded = msgspec.json.encode(obj, enc_hook=encode_hook)
    if indent is not None:
        encoded = msgspec.json.format(encoded, indent=indent)
    return encoded  # type: ignore [no-any-return]


def msgspec_json_loads(s: bytes | str) -> Any:
    """Deserialize bytes to object."""
    return msgspec.json.decode(s)


def msgspec_to_builtins(obj: Any) -> Any:
    """Convert object to built-in types."""
    return msgspec.to_builtins(obj, enc_hook=encode_hook)


def msgspec_to_schema(type: Any) -> Any:
    """Generate JSON schema for a given type."""
    if msgspec is None:  # pragma: no cover
        raise ImportError("msgspec is required for this function")
    return msgspec.json.schema(type, schema_hook=schema_hook)


def std_json_dumps(obj: Any, *, indent: int | None = None) -> bytes:
    """Serialize object to bytes."""
    return json.dumps(obj, default=std_to_builtins, indent=indent).encode("utf-8")


def std_json_loads(s: bytes | str) -> Any:
    """Deserialize bytes to object."""
    return json.loads(s)


def std_to_builtins(obj: Any) -> Any:
    """Convert object to built-in types."""
    if isinstance(obj, Mapping):
        return {k: std_to_builtins(v) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        return [std_to_builtins(v) for v in obj]
    return encode_hook(obj, raises=False)


if msgspec is None:  # pragma: no cover
    json_dumps = std_json_dumps
    json_loads = std_json_loads
    to_builtins = std_to_builtins
else:
    json_dumps = msgspec_json_dumps
    json_loads = msgspec_json_loads
    to_builtins = msgspec_to_builtins
