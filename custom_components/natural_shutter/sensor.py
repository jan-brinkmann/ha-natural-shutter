"""Expose stored setting values as ordinary Recorder-compatible sensors."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NaturalShutterConfigEntry
from .const import BUFFER, TARGET
from .entity import NaturalShutterEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NaturalShutterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add two always-available history sensors reporting saved settings."""
    async_add_entities([ShutterSettingSensor(entry, key) for key in (TARGET, BUFFER)])


class ShutterSettingSensor(NaturalShutterEntity, SensorEntity):
    """Report a saved percentage without long-term statistical aggregation."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0

    def __init__(self, entry: NaturalShutterConfigEntry, key: str) -> None:
        """Create a translated history sensor with a sensor-specific unique ID."""
        super().__init__(entry, key, "sensor")
        self._attr_icon = "mdi:chart-timeline-variant"

    @property
    def native_value(self) -> int:
        """Return only the persistent setting used by the associated slider."""
        return self.controller.values[self.key]
