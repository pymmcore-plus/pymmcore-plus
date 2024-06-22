from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    class json:
        """Namespace for JSON serialization."""

        @staticmethod
        def dumps(obj: Any, *, indent: int | None = None) -> bytes:
            """Serialize object to bytes."""

        @staticmethod
        def loads(s: bytes | str) -> Any:
            """Deserialize bytes to object."""


try:
    import msgspec

    def _enc_hook(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        raise NotImplementedError(f"Cannot serialize object of type {type(obj)}")

    def _dec_hook(type: type, obj: Any) -> Any:
        if hasattr(type, "model_validate"):
            return type.model_validate(obj)
        raise NotImplementedError(f"Cannot deserialize object of type {type}")

    class json:  # type: ignore
        """Namespace for JSON serialization."""

        @staticmethod
        def dumps(obj: Any, *, indent: int | None = None) -> bytes:
            """Serialize object to bytes."""
            encoded = msgspec.json.encode(obj, enc_hook=_enc_hook)
            if indent is not None:
                encoded = msgspec.json.format(encoded, indent=indent)
            return encoded  # type: ignore [no-any-return]

        @staticmethod
        def loads(s: bytes | str) -> Any:
            """Deserialize bytes to object."""
            return msgspec.json.decode(s, dec_hook=_dec_hook)

except ImportError:
    import json as _json

    class json:  # type: ignore
        """Namespace for JSON serialization."""

        @staticmethod
        def dumps(obj: Any, *, indent: int | None = None) -> bytes:
            """Serialize object to bytes."""
            return _json.dumps(obj, indent=indent).encode("utf-8")

        @staticmethod
        def loads(s: bytes | str) -> Any:
            """Deserialize bytes to object."""
            return _json.loads(s)
