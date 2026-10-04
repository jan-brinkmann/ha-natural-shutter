"""Verify setting transitions are available through ordinary HA Recorder history."""

from datetime import timedelta
from functools import partial

import pytest
from homeassistant.components.recorder import get_instance, history
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.natural_shutter.const import BUFFER, TARGET

from .conftest import SimulatedCover, set_setting, setting_entity_id


@pytest.fixture
def mock_recorder_before_hass(recorder_db_url):
    """Initialize the Recorder test database before creating the HA fixture."""


@pytest.fixture
async def cover(hass, async_setup_recorder_instance):
    """Start Recorder before entity-registry tracking, then add the simulated cover."""
    await async_setup_recorder_instance(hass)
    assert await async_setup_component(hass, "cover", {})
    source = SimulatedCover()
    await hass.data["cover"].async_add_entities([source])
    await hass.async_block_till_done()
    return source


async def test_recorder_stores_setting_transitions(hass, cover, add_shutter):
    """Record numeric setting changes in isolated SQLite without device actions."""
    recorder = get_instance(hass)
    start = dt_util.utcnow() - timedelta(seconds=1)
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    await set_setting(hass, entry, TARGET, 80)
    await set_setting(hass, entry, TARGET, 80)
    await async_wait_recording_done(hass)
    target_id = setting_entity_id(hass, entry, "sensor", TARGET)
    buffer_id = setting_entity_id(hass, entry, "sensor", BUFFER)
    states = await recorder.async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            entity_ids=[target_id, buffer_id],
            significant_changes_only=False,
        )
    )
    assert [state.state for state in states[target_id]] == ["30", "70", "80"]
    assert [state.state for state in states[buffer_id]] == ["0", "100"]
    assert cover.commands == []
