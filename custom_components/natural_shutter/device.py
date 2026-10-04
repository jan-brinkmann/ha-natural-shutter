"""Maintain reciprocal device links by updating only the owned virtual device."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, NAME
from .source import resolve_source


class ShutterDeviceLink:
    """Share source identifiers on a separate device owned by this config entry.

    Home Assistant 2026.8 scopes identifiers and connections to config entries.
    Shared keys make the devices appear in each other's Linked devices list
    without merging devices, moving entities, or modifying the source device.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Prepare registry tracking without creating or changing any device."""
        self.hass = hass
        self.entry = entry
        self._active = False
        self._device_id: str | None = None
        self._unsubscribe: CALLBACK_TYPE | None = None

    @callback
    def async_start(self) -> None:
        """Register the virtual device, synchronize its link, and track changes."""
        self._active = True
        self.async_refresh()
        self._unsubscribe = self.hass.bus.async_listen(
            dr.EVENT_DEVICE_REGISTRY_UPDATED, self._async_device_registry_changed
        )

    @callback
    def async_stop(self) -> None:
        """Detach tracking and prevent late events from changing registry data."""
        self._active = False
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def async_refresh(self) -> None:
        """Replace the owned device's link keys using the current registered source.

        Keep a stable Natural Shutter identifier and remove stale source keys.
        Sources without a device remain unlinked. A child device links through
        its parent actuator because HA's Linked devices API lists main devices.
        Registry changes never save settings or dispatch movement commands.
        """
        if not self._active:
            return
        registry = dr.async_get(self.hass)
        own = registry.async_get_device_by_identifier(
            (DOMAIN, self.entry.entry_id), self.entry.entry_id
        )
        if own is None:
            own = registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={(DOMAIN, self.entry.entry_id)},
                name=self.entry.title,
                manufacturer=NAME,
                model="Shutter settings",
            )
        self._device_id = own.id
        source_id = resolve_source(self.hass, self.entry.data)
        entity = er.async_get(self.hass).async_get(source_id) if source_id else None
        source = (
            registry.async_get(entity.device_id)
            if entity and entity.device_id
            else None
        )
        if source is not None and (
            parent_id := getattr(source, "parent_device_id", None)
        ):
            source = registry.async_get(parent_id)
        identifiers = {(DOMAIN, self.entry.entry_id)}
        connections: set[tuple[str, str]] = set()
        if source is not None:
            identifiers.update(source.identifiers)
            connections.update(source.connections)
        if own.identifiers != identifiers or own.connections != connections:
            registry.async_update_device(
                own.id, new_identifiers=identifiers, new_connections=connections
            )

    @callback
    def _async_device_registry_changed(self, event: Event) -> None:
        """Follow source device metadata and ignore updates to the virtual device."""
        if event.data["device_id"] != self._device_id:
            self.async_refresh()
