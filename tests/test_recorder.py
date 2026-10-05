"""Verify saved settings and position-decision entries through HA Recorder."""

from datetime import timedelta
from functools import partial

import pytest
from homeassistant.components.logbook.helpers import async_filter_entities
from homeassistant.components.logbook.models import LogbookConfig
from homeassistant.components.logbook.processor import EventProcessor
from homeassistant.components.recorder import get_instance, history
from homeassistant.const import EVENT_LOGBOOK_ENTRY
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.natural_shutter.const import BUFFER, TARGET

from .conftest import SimulatedCover, advance_time, set_setting, setting_entity_id


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


async def test_recorder_stores_passive_final_positions(hass, cover, add_shutter):
    """Persist automatic final-position transitions in history without cover commands."""
    recorder = get_instance(hass)
    start = dt_util.utcnow() - timedelta(seconds=1)
    entry = await add_shutter(cover)
    cover.report(40)
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    cover.report(30, motion="closing")
    await hass.async_block_till_done()
    cover.report(20)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    await async_wait_recording_done(hass)
    target_id = setting_entity_id(hass, entry, "sensor", TARGET)
    states = await recorder.async_add_executor_job(
        partial(
            history.get_significant_states,
            hass,
            start,
            entity_ids=[target_id],
            significant_changes_only=False,
        )
    )
    assert [state.state for state in states[target_id]] == ["30", "60", "80"]
    assert cover.commands == []


@pytest.mark.parametrize("decision", ["suppressed", "command", "external"])
async def test_decisions_are_in_entity_and_device_activity(
    hass, cover, add_shutter, decision
):
    """Retrieve commands, suppression, and external alignment through Activity filters."""
    hass.data["logbook"] = LogbookConfig({}, None, None)
    recorder = get_instance(hass)
    start = dt_util.utcnow() - timedelta(seconds=1)
    entry = await add_shutter(cover)
    buffer = 100 if decision == "suppressed" else 10
    if decision == "external":
        cover.report(40)
        await hass.async_block_till_done()
        await advance_time(hass, 11)
    else:
        await set_setting(hass, entry, BUFFER, buffer)
        await set_setting(hass, entry, TARGET, 70)
    await async_wait_recording_done(hass)
    target_id = setting_entity_id(hass, entry, "number", TARGET)
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("natural_shutter", entry.entry_id), entry.entry_id
    )
    assert device is not None
    device_entities = [
        entity.entity_id
        for entity in er.async_entries_for_device(er.async_get(hass), device.id)
    ]
    for filters in (
        {"entity_ids": [target_id]},
        {"entity_ids": device_entities, "device_ids": [device.id]},
    ):
        filters["entity_ids"] = async_filter_entities(hass, filters["entity_ids"])
        processor = EventProcessor(hass, [EVENT_LOGBOOK_ENTRY], **filters)
        events = await recorder.async_add_executor_job(
            processor.get_events, start, dt_util.utcnow() + timedelta(seconds=1)
        )
        messages = [event for event in events if "message" in event]
        assert len(messages) == 1
        assert messages[0]["entity_id"] == target_id
        assert messages[0]["domain"] == "natural_shutter"
        reason = (
            "Difference below buffer"
            if decision == "suppressed"
            else "Position command sent to source cover"
            if decision == "command"
            else "Target updated after an external position change"
        )
        assert reason in messages[0]["message"]
        if decision == "external":
            assert "Target 30 → 60 %, actual 60 % (HA 40 %)" in messages[0]["message"]
        else:
            assert f"difference 40 pp, buffer {buffer} pp" in messages[0]["message"]
    assert cover.commands == ([30] if decision == "command" else [])
