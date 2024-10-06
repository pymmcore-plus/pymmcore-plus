from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Container, MutableMapping
    from typing import Final

    from typing_extensions import Self  # py311

    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.metadata.schema import ConfigGroup as ConfigGroupMeta
    from pymmcore_plus.metadata.schema import ConfigPreset as ConfigPresetMeta

    from ._core_link import ErrCallback


UNDEFINED: Final = "UNDEFINED"
DEFAULT_AFFINE: Final = (1, 0, 0, 0, 1, 0)
PIXEL_SIZE_GROUP: Final = "PixelSizeGroup"


class Setting(NamedTuple):
    """Model of a device setting."""

    device_name: str = UNDEFINED
    property_name: str = UNDEFINED
    property_value: str = UNDEFINED

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.device_name!r}, "
            f"{self.property_name!r}, {self.property_value!r}))"
        )


@dataclass
class ConfigPreset:
    """ConfigPreset model."""

    name: str
    settings: list[Setting] = field(default_factory=list)

    @classmethod
    def from_metadata(cls, meta: ConfigPresetMeta) -> Self:
        return cls(
            name=meta["name"],
            settings=[
                Setting(
                    device_name=d["dev"],
                    property_name=d["prop"],
                    property_value=d["val"],
                )
                for d in meta["settings"]
            ],
        )


@dataclass
class ConfigGroup:
    """ConfigGroup model."""

    name: str
    presets: MutableMapping[str, ConfigPreset] = field(default_factory=dict)

    @classmethod
    def from_metadata(cls, meta: ConfigGroupMeta) -> Self:
        presets = {
            preset["name"]: ConfigPreset.from_metadata(preset)
            for preset in meta["presets"]
        }
        return cls(name=meta["name"], presets=presets)

    @classmethod
    def create_from_core(cls, core: CMMCorePlus, name: str) -> Self:
        obj = cls(name=name)
        obj.update_from_core(core)
        return obj

    def update_from_core(self, core: CMMCorePlus) -> None:
        """Update this object's values from the core."""
        self.presets = {
            preset: ConfigPreset(
                name=preset,
                settings=[Setting(*d) for d in core.getConfigData(self.name, preset)],
            )
            for preset in core.getAvailableConfigs(self.name)
        }

    @staticmethod
    def all_config_groups(core: CMMCorePlus) -> dict[str, ConfigGroup]:
        """Get all config presets from the given core."""
        return {
            group: ConfigGroup.create_from_core(core, group)
            for group in core.getAvailableConfigGroups()
        }

    def apply_to_core(
        self,
        core: CMMCorePlus,
        *,
        exclude: Container[str] = (),
        on_err: ErrCallback | None = None,
        apply_properties: bool = False,
        then_update: bool = True,
    ) -> None:
        if self.name not in core.getAvailableConfigGroups():
            core.defineConfigGroup(self.name)
        for config_name, preset in self.presets.items():
            for dev, prop, val in preset.settings:
                core.defineConfig(self.name, config_name, dev, prop, val)

        if then_update:
            self.update_from_core(core)  # pragma: no cover
