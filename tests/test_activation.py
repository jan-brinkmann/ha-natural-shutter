"""Verify per-mapping activation, persistence, availability, and ordered writes."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.natural_shutter.const import BUFFER, ENABLED, TARGET, storage_key
from custom_components.natural_shutter.controller import ShutterController

from .conftest import SimulatedCover, set_enabled, set_setting, setting_entity_id


async def test_activation_entities_and_disabled_settings(hass, cover, add_shutter):
    """Create disabled and keep switch/history synchronized with editable sliders."""
    entry = await add_shutter(cover, enabled=False)
    switch_id = setting_entity_id(hass, entry, "switch", ENABLED)
    sensor_id = setting_entity_id(hass, entry, "binary_sensor", ENABLED)
    for entity_id in (switch_id, sensor_id):
        assert hass.states.get(entity_id).state == "off"
    await set_setting(hass, entry, TARGET, 70)
    await set_setting(hass, entry, BUFFER, 10)
    assert entry.runtime_data.values == {TARGET: 70, BUFFER: 10}
    for entity_id in (switch_id, sensor_id):
        assert hass.states.get(entity_id).state == "off"
    sensor_state = hass.states.get(sensor_id)
    await set_enabled(hass, entry, False)
    assert hass.states.get(sensor_id) is sensor_state
    await set_enabled(hass, entry, True)
    assert hass.states.get(switch_id).state == hass.states.get(sensor_id).state == "on"
    assert entry.runtime_data.values == {TARGET: 70, BUFFER: 10}
    assert cover.commands == []
    await set_setting(hass, entry, TARGET, 80)
    assert cover.commands == [20]


async def test_disabled_offline_target_is_editable(hass, cover, add_shutter):
    """Accept disabled target edits without a source and restore availability on enable."""
    entry = await add_shutter(cover)
    target_id = setting_entity_id(hass, entry, "number", TARGET)
    cover.report(70, available=False)
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state == STATE_UNAVAILABLE
    await set_enabled(hass, entry, False)
    assert hass.states.get(target_id).state == "30"
    await set_setting(hass, entry, TARGET, 70)
    await set_setting(hass, entry, BUFFER, 15)
    assert entry.runtime_data.values == {TARGET: 70, BUFFER: 15}
    await set_enabled(hass, entry, True)
    assert hass.states.get(target_id).state == STATE_UNAVAILABLE
    cover.report(70)
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state == "70"
    assert cover.commands == []


async def test_activation_is_independent_per_mapping(hass, cover, add_shutter):
    """Disabling one virtual device leaves another device's commands enabled."""
    other = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other])
    first = await add_shutter(cover)
    second = await add_shutter(other)
    await set_enabled(hass, first, False)
    await set_setting(hass, first, TARGET, 60)
    await set_setting(hass, second, TARGET, 60)
    assert first.runtime_data.enabled is False
    assert second.runtime_data.enabled is True
    assert cover.commands == []
    assert other.commands == [40]
    await set_enabled(hass, second, False)
    await set_enabled(hass, first, True)
    assert first.runtime_data.enabled is True
    assert second.runtime_data.enabled is False
    assert cover.commands == []
    assert other.commands == [40]


@pytest.mark.parametrize("available", [True, False])
async def test_reload_retains_activation(
    hass, hass_storage, cover, add_shutter, available
):
    """Restore disabled activation and settings without moving or replaying targets."""
    entry = await add_shutter(cover)
    await set_enabled(hass, entry, False)
    await set_setting(hass, entry, TARGET, 60)
    await set_setting(hass, entry, BUFFER, 15)
    cover.report(5, available=available)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    expected_target = 95 if available else 60
    assert entry.runtime_data.enabled is False
    assert entry.runtime_data.values == {TARGET: expected_target, BUFFER: 15}
    assert hass_storage[storage_key(entry.entry_id)]["data"] == {
        TARGET: expected_target,
        BUFFER: 15,
        ENABLED: False,
    }
    for kind in ("switch", "binary_sensor"):
        assert (
            hass.states.get(setting_entity_id(hass, entry, kind, ENABLED)).state
            == "off"
        )
    assert cover.commands == []


async def test_legacy_storage_defaults_to_enabled(
    hass, hass_storage, cover, add_shutter
):
    """Add enabled activation to existing percentage-only storage without a command."""
    entry = await add_shutter(cover)
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass_storage[storage_key(entry.entry_id)]["data"] = {TARGET: 60, BUFFER: 15}
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.enabled is True
    assert hass_storage[storage_key(entry.entry_id)]["data"] == {
        TARGET: 30,
        BUFFER: 15,
        ENABLED: True,
    }
    assert cover.commands == []


@pytest.mark.parametrize("enabled", [0, 1, None, "false", [], {}])
async def test_invalid_saved_activation_stops_setup(
    hass, hass_storage, cover, add_shutter, enabled
):
    """Reject damaged activation instead of silently enabling or disabling commands."""
    entry = await add_shutter(cover)
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass_storage[storage_key(entry.entry_id)]["data"][ENABLED] = enabled
    with pytest.raises(HomeAssistantError) as error:
        await ShutterController(hass, entry).async_load()
    assert error.value.translation_key == "invalid_storage"
    assert cover.commands == []


async def test_failed_activation_save_and_unloaded_write(hass, cover, add_shutter):
    """Preserve activation on save failure and reject activation writes after unload."""
    entry = await add_shutter(cover)
    controller = entry.runtime_data
    with patch.object(controller.store, "async_save", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            await set_enabled(hass, entry, False)
    assert controller.enabled is True
    for kind in ("switch", "binary_sensor"):
        assert (
            hass.states.get(setting_entity_id(hass, entry, kind, ENABLED)).state == "on"
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError) as error:
        await controller.async_set_enabled(False)
    assert error.value.translation_key == "entry_unloaded"
    assert cover.commands == []


async def test_activation_joins_target_write_order(hass, cover, add_shutter):
    """Finish an in-flight command before disabling and suppress later target writes."""
    entry = await add_shutter(cover)
    controller = entry.runtime_data
    cover.gate = asyncio.Event()
    first = asyncio.create_task(controller.async_set_value(TARGET, 20))
    await cover.command_started.wait()
    disable = asyncio.create_task(controller.async_set_enabled(False))
    later = asyncio.create_task(controller.async_set_value(TARGET, 60))
    await asyncio.sleep(0)
    assert controller.enabled is True
    assert cover.commands == [80]
    cover.gate.set()
    await asyncio.gather(first, disable, later)
    assert controller.enabled is False
    assert controller.values[TARGET] == 60
    assert cover.commands == [80]
