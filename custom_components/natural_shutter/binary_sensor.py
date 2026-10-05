"""Expose persistent activation as a Recorder-compatible history sensor."""

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Add one always-available activation history sensor to this virtual device."""
    async_add_entities([ShutterEnabledSensor(entry)])


class ShutterEnabledSensor(NaturalShutterEntity, BinarySensorEntity):
    """Record activation changes independently of source availability."""

    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, entry: NaturalShutterConfigEntry) -> None:
        """Bind a translated read-only sensor with its own stable unique ID."""
        super().__init__(entry, ENABLED, "binary_sensor")

    @property
    def is_on(self) -> bool:
        """Return the activation setting shared with this mapping's switch."""
        return self.controller.enabled
