"""Expose independent target and buffer sliders with an explicit write path."""

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Add exactly two setting sliders for one manually selected cover."""
    async_add_entities([ShutterNumber(entry, key) for key in (TARGET, BUFFER)])


class ShutterNumber(NaturalShutterEntity, NumberEntity):
    """Expose saved percentages, with target availability following the source."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: NaturalShutterConfigEntry, key: str) -> None:
        """Create a translated slider with a stable number-specific identity."""
        super().__init__(entry, key, "number")
        self._attr_icon = (
            "mdi:window-shutter" if key == TARGET else "mdi:arrow-expand-vertical"
        )

    @property
    def available(self) -> bool:
        """Keep the buffer available and expose the target only with a live source."""
        return self.key == BUFFER or self.controller.source_available

    @property
    def native_value(self) -> int:
        """Return the stored setting, never the cover's actual position."""
        return self.controller.values[self.key]

    async def async_set_native_value(self, value: float) -> None:
        """Handle an explicit user or action write with its originating context."""
        await self.controller.async_set_value(self.key, value, self._context)
