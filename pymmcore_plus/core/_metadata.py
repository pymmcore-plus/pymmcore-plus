"""pythonic wrapper on pymmcore.Metadata object."""
from collections.abc import Mapping
from typing import Any, ItemsView, Iterator, KeysView, ValuesView

import pymmcore


class MetaKeysView(KeysView[str]):
    def __init__(self, metadata: "Metadata") -> None:
        super().__init__(metadata)
        self._metadata = metadata

    def __iter__(self) -> Iterator[str]:
        """Yield headers."""
        yield from self._metadata

    def __repr__(self) -> str:
        return f"metadata_keys({list(self)!r})"


class MetaItemsView(ItemsView[str, Any]):
    """dictionary view for Table items."""

    def __init__(self, mapping: "Metadata") -> None:
        super().__init__(mapping)
        self._mapping = mapping

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        """Yield items."""
        for key in self._mapping:
            yield (key, self._mapping.GetSingleTag(key).GetValue())

    def __repr__(self) -> str:
        return f"metadata_items({list(self)!r})"


_NULL = object()


class MetaValuesView(ValuesView[Any]):
    """dictionary view for Table items."""

    def __init__(self, mapping: "Metadata") -> None:
        super().__init__(mapping)
        self._mapping = mapping

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        """Yield items."""
        for key in self._mapping:
            yield self._mapping.GetSingleTag(key).GetValue()

    def __repr__(self) -> str:
        return f"metadata_values({list(self)!r})"


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
        return f"Metadata({dict(self)!r})"

    def get(self, name, default=_NULL):
        try:
            return self.__getitem__(name)
        except KeyError:
            if default is not _NULL:
                return default
            raise

    def copy(self):
        return type(self)(**dict(self))

    def keys(self) -> MetaKeysView:
        return MetaKeysView(self)

    def items(self) -> MetaItemsView:
        return MetaItemsView(self)

    def values(self) -> MetaValuesView:
        return MetaValuesView(self)

    def clear(self) -> None:
        self.Clear()

    def __eq__(self, other) -> bool:
        if not isinstance(other, Metadata):
            return False
        return dict(self) == dict(other)

    def json(self) -> str:
        import json

        return json.dumps(dict(self))
