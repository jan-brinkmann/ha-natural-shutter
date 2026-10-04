"""Share translated entity identities, device grouping, and value subscriptions."""

from homeassistant.helpers.entity import DeviceInfo, Entity

from . import NaturalShutterConfigEntry
from .const import DOMAIN, NAME


class NaturalShutterEntity(Entity):
    """Represent one persistent setting on an integration-owned virtual device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: NaturalShutterConfigEntry, key: str, kind: str) -> None:
        """Bind to the controller using a unique identity independent of entity IDs."""
        self.controller = entry.runtime_data
        self.key = key
        self._attr_unique_id = f"{entry.entry_id}_{kind}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=NAME,
            model="Shutter settings",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to setting and availability updates; clean up on entity removal."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.controller.async_subscribe(self.key, self.async_write_ha_state)
        )
