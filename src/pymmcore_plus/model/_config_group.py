from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Container, MutableMapping, NamedTuple

if TYPE_CHECKING:
    from typing import Final

    from pymmcore_plus import CMMCorePlus

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


@dataclass
class ConfigGroup:
    """ConfigGroup model."""

    name: str
    presets: MutableMapping[str, ConfigPreset] = field(default_factory=dict)

    @classmethod
    def create_from_core(cls, core: CMMCorePlus, name: str) -> ConfigGroup:
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
