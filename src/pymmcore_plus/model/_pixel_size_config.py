from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING

from ._config_group import ConfigGroup, ConfigPreset, Setting

if TYPE_CHECKING:
    from collections.abc import Container, Iterable, MutableMapping
    from typing import Any, Final

    from typing_extensions import (
        Self,  # py311
        TypeAlias,  # py310
    )

    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.metadata.schema import PixelSizeConfigPreset

    from ._core_link import ErrCallback

    AffineTuple: TypeAlias = tuple[float, float, float, float, float, float]

DEFAULT_AFFINE: Final[AffineTuple] = (1, 0, 0, 0, 1, 0)
PIXEL_SIZE_GROUP: Final = "PixelSizeGroup"


@dataclass
class PixelSizePreset(ConfigPreset):
    """PixelSizePreset model."""

    pixel_size_um: float = 0.0
    affine: AffineTuple = DEFAULT_AFFINE
    angle_dxdz: float = 0.0
    angle_dydz: float = 0.0
    optimalz_um: float = 0.0

    @classmethod
    def from_metadata(cls, meta: PixelSizeConfigPreset) -> Self:  # type: ignore [override]
        obj = super().from_metadata(meta)
        obj.pixel_size_um = meta["pixel_size_um"]
        if "pixel_size_affine" in meta:
            obj.affine = meta["pixel_size_affine"]
        if "pixel_size_dxdz" in meta:
            obj.angle_dxdz = meta["pixel_size_dxdz"]
        if "pixel_size_dydz" in meta:
            obj.angle_dydz = meta["pixel_size_dydz"]
        if "pixel_size_optimal_z_um" in meta:
            obj.optimalz_um = meta["pixel_size_optimal_z_um"]
        return obj

    def __rich_repr__(self, *, defaults: bool = False) -> Iterable[tuple[str, Any]]:
        """Make AvailableDevices look a little less verbose."""
        for f in fields(self):
            if f.repr is False:
                continue  # pragma: no cover
            val = getattr(self, f.name)
            default = f.default_factory() if callable(f.default_factory) else f.default
            if defaults or val != default:
                yield f.name, val


@dataclass
class PixelSizeGroup(ConfigGroup):
    """Model of the pixel size group."""

    name: str = PIXEL_SIZE_GROUP
    presets: MutableMapping[str, PixelSizePreset] = field(default_factory=dict)  # type: ignore

    @classmethod
    def from_metadata(cls, meta: tuple[PixelSizeConfigPreset, ...]) -> Self:  # type: ignore [override]
        """Create a PixelSizeGroup from metadata."""
        return cls(
            presets={
                preset_info["name"]: PixelSizePreset.from_metadata(preset_info)
                for preset_info in meta
            }
        )

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
                    affine=core.getPixelSizeAffineByID(preset),
                    settings=[Setting(*d) for d in core.getPixelSizeConfigData(preset)],
                )
                for preset in core.getAvailablePixelSizeConfigs()
            }
        )

    def apply_to_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
        apply_properties: bool = False,
        then_update: bool = True,
    ) -> None:
        for config_name, preset in self.presets.items():
            for dev, prop, val in preset.settings:
                core.definePixelSizeConfig(config_name, dev, prop, val)
            core.setPixelSizeUm(config_name, preset.pixel_size_um)
            core.setPixelSizeAffine(config_name, preset.affine)

        if then_update:
            self.update_from_core(core)  # pragma: no cover
