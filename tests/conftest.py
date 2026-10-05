"""Create isolated Home Assistant instances with simulated position covers."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.const import CONF_NAME, EVENT_LOGBOOK_ENTRY
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.natural_shutter.const import (
    CONF_NOTIFICATION_SERVICE,
    CONF_SOURCE,
    DOMAIN,
)


class SimulatedCover(CoverEntity):
    """Expose a controllable cover whose actions never communicate with hardware."""

    _attr_should_poll = False
    _attr_supported_features = CoverEntityFeature.SET_POSITION

    def __init__(self, name: str = "Living room", position: object = 70) -> None:
        """Initialize source metadata, a position, and action tracing gates."""
        self._attr_name = name
        self._attr_unique_id = name
        self._attr_current_cover_position = position
        self._attr_is_closed = False
        self.commands: list[int] = []
        self.fail = False
        self.gate: asyncio.Event | None = None
        self.command_started = asyncio.Event()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Record the requested HA position and optionally block or fail it."""
        self.commands.append(kwargs[ATTR_POSITION])
        self.command_started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise HomeAssistantError("Simulated device failure")

    def report(
        self,
        position: object = 70,
        available: bool = True,
        motion: str | None = None,
        context: Context | None = None,
    ) -> None:
        """Publish position and motion, optionally with an explicit originating context."""
        self._attr_current_cover_position = position
        self._attr_available = available
        self._attr_is_opening = motion == "opening"
        self._attr_is_closing = motion == "closing"
        if context is not None:
            self.async_set_context(context)
        self.async_write_ha_state()


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable loading this working tree's integration in each isolated test."""


@pytest.fixture
async def cover(hass: HomeAssistant) -> SimulatedCover:
    """Set up the real HA cover service with a simulated registry-backed cover."""
    assert await async_setup_component(hass, "cover", {})
    entity = SimulatedCover()
    await hass.data["cover"].async_add_entities([entity])
    await hass.async_block_till_done()
    return entity


@pytest.fixture
def add_shutter(hass: HomeAssistant) -> Callable[..., Coroutine[Any, Any, ConfigEntry]]:
    """Return a helper that creates an entry using the actual manual config flow."""

    async def add(entity: SimulatedCover, name: str | None = None) -> ConfigEntry:
        """Create a mapping and wait until its numbers and sensors are loaded."""
        data = {CONF_SOURCE: entity.entity_id}
        if name is not None:
            data[CONF_NAME] = name
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=data
        )
        assert result["type"] == "create_entry", result
        await hass.async_block_till_done()
        assert entity.commands == []
        return result["result"]

    return add


def setting_entity_id(
    hass: HomeAssistant, entry: ConfigEntry, kind: str, key: str
) -> str:
    """Resolve a generated entity by its stable unique ID, regardless of language."""
    entity_id = er.async_get(hass).async_get_entity_id(
        kind, DOMAIN, f"{entry.entry_id}_{kind}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def set_setting(
    hass: HomeAssistant, entry: ConfigEntry, key: str, value: float
) -> None:
    """Write through number.set_value and wait for sensor state publication."""
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": setting_entity_id(hass, entry, "number", key), "value": value},
        blocking=True,
    )
    await hass.async_block_till_done()


async def advance_time(hass: HomeAssistant, seconds: float) -> None:
    """Fire scheduled HA callbacks the given seconds ahead without sleeping."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


@pytest.fixture
def activity_events(hass):
    """Collect real Activity events and detach the observer after the test."""
    events = []
    remove = hass.bus.async_listen(EVENT_LOGBOOK_ENTRY, events.append)
    yield events
    remove()


@pytest.fixture
def phone(hass):
    """Register a simulated Companion App service without sending real messages."""
    receive = AsyncMock()
    hass.services.async_register("notify", "mobile_app_test_phone", receive)
    return receive


async def select_phone(hass, entry, service="mobile_app_test_phone"):
    """Configure a notifier through HA's actual Options Flow without reload."""
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_NOTIFICATION_SERVICE: service}
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.options[CONF_NOTIFICATION_SERVICE] == service
