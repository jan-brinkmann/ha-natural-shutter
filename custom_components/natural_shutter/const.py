"""Define shared names, storage keys, and entity settings."""

from homeassistant.const import Platform

DOMAIN = "natural_shutter"
NAME = "Natural Shutter"
MIN_HA_VERSION = "2026.8.0"
PLATFORMS = (Platform.NUMBER, Platform.SENSOR)

CONF_SOURCE = "source_entity_id"
CONF_SOURCE_REGISTRY_ID = "source_registry_id"
CONF_INITIAL_TARGET = "initial_target"
CONF_NOTIFICATION_SERVICE = "notification_service"
CONF_POSITION_QUIET_SECONDS = "position_quiet_seconds"
DEFAULT_POSITION_QUIET_SECONDS = 10
POSITION_SETTLE_SECONDS = 2
COMMAND_TRACK_SECONDS = 300
DATA_POSITION_COMMANDS = f"{DOMAIN}_position_commands"
MOBILE_APP_SERVICE_PREFIX = "mobile_app_"
TARGET = "target_position"
BUFFER = "buffer"
STORAGE_VERSION = 1


def storage_key(entry_id: str) -> str:
    """Return the Home Assistant storage key for one mapping."""
    return f"{DOMAIN}.{entry_id}"
