"""Define shared names, storage keys, and entity settings."""

from homeassistant.const import Platform

DOMAIN = "natural_shutter"
NAME = "Natural Shutter"
MIN_HA_VERSION = "2026.8.0"
PLATFORMS = (Platform.NUMBER, Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR)

CONF_SOURCE = "source_entity_id"
CONF_SOURCE_REGISTRY_ID = "source_registry_id"
CONF_INITIAL_TARGET = "initial_target"
CONF_NOTIFICATION_SERVICE = "notification_service"
MOBILE_APP_SERVICE_PREFIX = "mobile_app_"
TARGET = "target_position"
BUFFER = "buffer"
ENABLED = "enabled"
STORAGE_VERSION = 1


def storage_key(entry_id: str) -> str:
    """Return the Home Assistant storage key for one mapping."""
    return f"{DOMAIN}.{entry_id}"
