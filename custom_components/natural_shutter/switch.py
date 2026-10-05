"""Expose each mapping's persistent activation without triggering movement."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NaturalShutterConfigEntry
from .const import ENABLED
from .entity import NaturalShutterEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NaturalShutterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one always-available activation switch to this virtual device."""
    async_add_entities([ShutterEnabledSwitch(entry)])


class ShutterEnabledSwitch(NaturalShutterEntity, SwitchEntity):
    """Control only this mapping's saved activation state."""

    _attr_icon = "mdi:power"

    def __init__(self, entry: NaturalShutterConfigEntry) -> None:
        """Bind the translated switch to this entry's activation subscription."""
        super().__init__(entry, ENABLED, "switch")

    @property
    def is_on(self) -> bool:
        """Return whether this mapping may dispatch new target commands."""
        return self.controller.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable future target writes without replaying a saved target."""
        await self.controller.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable future target commands and suppression phone notifications."""
        await self.controller.async_set_enabled(False)
