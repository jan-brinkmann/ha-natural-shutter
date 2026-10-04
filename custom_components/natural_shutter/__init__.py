"""Set up manually selected Natural Shutter mappings and their settings."""

from awesomeversion import AwesomeVersion
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MIN_HA_VERSION, PLATFORMS, STORAGE_VERSION, storage_key
from .controller import ShutterController

type NaturalShutterConfigEntry = ConfigEntry[ShutterController]


async def async_setup_entry(
    hass: HomeAssistant, entry: NaturalShutterConfigEntry
) -> bool:
    """Require safe device isolation, then load one mapping without movement.

    Older HA versions would merge shared identifiers into the actuator's device.
    Reject setup before accessing settings or devices on those versions.
    """
    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="unsupported_home_assistant",
            translation_placeholders={"version": MIN_HA_VERSION},
        )
    controller = ShutterController(hass, entry)
    try:
        await controller.async_load()
        entry.runtime_data = controller
        entry.async_on_unload(controller.async_stop)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        controller.async_stop()
        raise
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: NaturalShutterConfigEntry
) -> bool:
    """Unload entities and drain active writes while retaining persistent settings."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_close()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete only this mapping's settings after the user removes its entry."""
    await Store(hass, STORAGE_VERSION, storage_key(entry.entry_id)).async_remove()
