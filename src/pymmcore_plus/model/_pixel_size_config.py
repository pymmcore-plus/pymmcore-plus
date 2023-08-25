from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any, Iterable, MutableMapping, TypeAlias

from ._config_group import ConfigGroup, ConfigPreset, Setting

if TYPE_CHECKING:
    from typing import Final

    from pymmcore_plus import CMMCorePlus

    AffineTuple: TypeAlias = tuple[float, float, float, float, float, float]

DEFAULT_AFFINE: Final[AffineTuple] = (1, 0, 0, 0, 1, 0)
PIXEL_SIZE_GROUP: Final = "PixelSizeGroup"


@dataclass
class PixelSizePreset(ConfigPreset):
    """PixelSizePreset model."""

    pixel_size_um: float = 0.0
    affine: AffineTuple = DEFAULT_AFFINE

    def __rich_repr__(self, *, defaults: bool = False) -> Iterable[tuple[str, Any]]:
        """Make AvailableDevices look a little less verbose."""
        for f in fields(self):
            if f.repr is False:
                continue
            val = getattr(self, f.name)
            default = f.default_factory() if callable(f.default_factory) else f.default
            if defaults or val != default:
                yield f.name, val


@dataclass
class PixelSizeGroup(ConfigGroup):
    """Model of the pixel size group."""

    name: str = PIXEL_SIZE_GROUP
    presets: MutableMapping[str, PixelSizePreset] = field(default_factory=dict)

    @classmethod
    def create_from_core(
        cls, core: CMMCorePlus, name: str = PIXEL_SIZE_GROUP
    ) -> PixelSizeGroup:
        """Create pixel size presets from the given core."""
        return cls(
            presets={
                preset: PixelSizePreset(
                    name=preset,
                    pixel_size_um=core.getPixelSizeUmByID(preset),
                    affine=core.getPixelSizeAffineByID(preset),  # type: ignore
                    settings=[Setting(*d) for d in core.getPixelSizeConfigData(preset)],
                )
                for preset in core.getAvailablePixelSizeConfigs()
            }
        )
