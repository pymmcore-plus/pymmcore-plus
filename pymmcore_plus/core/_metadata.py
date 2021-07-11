"""pythonic wrapper on pymmcore.Metadata object."""
from collections.abc import Mapping
from types import new_class
from typing import Any, ItemsView, Iterator, KeysView, ValuesView

import pymmcore

_NULL = object()


class Metadata(pymmcore.Metadata):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        if args and isinstance(args[0], Mapping):
            for k, v in args[0].items():
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def __getitem__(self, name: str) -> Any:
        try:
            return self.GetSingleTag(name).GetValue()
        except ValueError:
            raise KeyError(str(name))

    def __setitem__(self, name: str, value: Any) -> None:
        tag = pymmcore.MetadataSingleTag(name, "_", False)
        tag.SetValue(str(value))
        self.SetTag(tag)

    def __delitem__(self, name: str) -> None:
        self.RemoveTag(name)

    def __iter__(self) -> Iterator[str]:
        yield from self.GetKeys()

    def __contains__(self, tag: str):
        return self.HasTag(tag)

    def __len__(self) -> int:
        return len(self.GetKeys())

    def __repr__(self):
        return f"{dict(self)!r}"

    def get(self, name, default=_NULL):
        try:
            return self.__getitem__(name)
        except KeyError:
            if default is not _NULL:
                return default
            raise

    def copy(self):
        return type(self)(**dict(self))

    def clear(self) -> None:
        self.Clear()

    def __eq__(self, other) -> bool:
        if not isinstance(other, Metadata):
            return False
        return dict(self) == dict(other)

    def json(self) -> str:
        import json

        return json.dumps(dict(self))

    def keys(self) -> KeysView[str]:
        return metadata_keys(self)

    def items(self) -> ItemsView[str, str]:
        return metadata_items(self)

    def values(self) -> ValuesView[str]:
        return metadata_values(self)


metadata_keys = new_class("metadata_keys", (KeysView,), {})
metadata_items = new_class("metadata_items", (ItemsView,), {})
metadata_values = new_class("metadata_values", (ValuesView,), {})
