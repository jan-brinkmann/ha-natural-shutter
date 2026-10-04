"""Validate percentages and resolve cover identities without moving devices."""

import math
from collections.abc import Mapping
from typing import Any

from homeassistant.components.cover import ATTR_CURRENT_POSITION, CoverEntityFeature
from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_SOURCE, CONF_SOURCE_REGISTRY_ID


def valid_percentage(value: object) -> float | None:
    """Return a finite percentage, or None for invalid or out-of-range input."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def normalize_percentage(value: object) -> int:
    """Round valid input to whole percent, halves up; raise ValueError otherwise."""
    if (number := valid_percentage(value)) is None:
        raise ValueError("Expected a finite percentage between 0 and 100")
    return math.floor(number + 0.5)


def supports_position(features: object) -> bool:
    """Return whether a valid feature mask advertises absolute positioning."""
    return (
        isinstance(features, int)
        and not isinstance(features, bool)
        and features >= 0
        and bool(features & CoverEntityFeature.SET_POSITION)
    )


def current_position(state: State | None) -> float | None:
    """Read an available cover's actual position, rejecting restored states."""
    if (
        state is None
        or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        or state.attributes.get(ATTR_RESTORED)
    ):
        return None
    return valid_percentage(state.attributes.get(ATTR_CURRENT_POSITION))


def source_identity(data: Mapping[str, Any]) -> str:
    """Return a config-flow identity, preferring a stable registry record."""
    if registry_id := data.get(CONF_SOURCE_REGISTRY_ID):
        return f"registry:{registry_id}"
    return f"entity:{data[CONF_SOURCE]}"


@callback
def resolve_source(hass: HomeAssistant, data: Mapping[str, Any]) -> str | None:
    """Resolve a pinned registry identity; never fall back after its removal."""
    if registry_id := data.get(CONF_SOURCE_REGISTRY_ID):
        entry = er.async_get(hass).async_get(registry_id)
        return entry.entity_id if entry is not None else None
    return data[CONF_SOURCE]
