"""Verify non-actuating load alignment, identity tracking, and serialized writes."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import frame
from homeassistant.loader import DATA_CUSTOM_COMPONENTS
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_test_home_assistant,
)

from custom_components.natural_shutter.const import (
    BUFFER,
    CONF_SOURCE,
    DOMAIN,
    ENABLED,
    TARGET,
    storage_key,
)
from custom_components.natural_shutter.controller import ShutterController

from .conftest import SimulatedCover, set_enabled, set_setting, setting_entity_id


async def test_offline_reload_retains_target_without_actions(hass, cover, add_shutter):
    """Retain the saved target during an offline load and subsequent reconnection."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 60)
    previous = entry.runtime_data
    cover.report(5, available=False)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert previous._unsubscribe_registry is None
    assert previous._unsubscribe_source is None
    assert previous.device_link._unsubscribe is None
    assert previous._listeners == {TARGET: [], BUFFER: [], ENABLED: []}
    assert entry.runtime_data.values == {TARGET: 60, BUFFER: 100}
    assert len(entry.runtime_data._listeners[TARGET]) == 2
    assert len(entry.runtime_data._listeners[BUFFER]) == 2
    assert len(entry.runtime_data._listeners[ENABLED]) == 2
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    cover.report(5)
    await hass.async_block_till_done()
    assert entry.runtime_data.values == {TARGET: 60, BUFFER: 100}
    assert hass.states.get(number_id).state == "60"
    assert cover.commands == []


@pytest.mark.parametrize(
    "position, expected, buffer",
    [(0, 100, 0), (100, 0, 100), (25.5, 75, 15), (70, 30, 0)],
)
async def test_reload_aligns_target_without_actions(
    hass, hass_storage, cover, add_shutter, position, expected, buffer
):
    """Persist the inverted live position on reload without applying the buffer."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 60)
    await set_setting(hass, entry, BUFFER, buffer)
    cover.report(position)
    await hass.async_block_till_done()
    assert entry.runtime_data.values == {TARGET: 60, BUFFER: buffer}
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    values = {TARGET: expected, BUFFER: buffer}
    assert entry.runtime_data.values == values
    assert hass_storage[storage_key(entry.entry_id)]["data"] == {
        **values,
        ENABLED: True,
    }
    for kind in ("number", "sensor"):
        for key in (TARGET, BUFFER):
            assert hass.states.get(
                setting_entity_id(hass, entry, kind, key)
            ).state == str(values[key])
    assert cover.current_cover_position == position
    assert cover.commands == []
    cover.report(50)
    await hass.async_block_till_done()
    assert entry.runtime_data.values == values
    assert cover.commands == []


@pytest.mark.parametrize(
    "state, attributes",
    [
        ("unavailable", {"current_position": 5}),
        ("unknown", {"current_position": 5}),
        ("open", {}),
        ("open", {"current_position": None}),
        ("open", {"current_position": "nan"}),
        ("open", {"current_position": -1}),
        ("open", {"current_position": 101}),
        ("open", {"current_position": 5, "restored": True}),
        (None, {}),
    ],
)
async def test_reload_without_live_position_retains_target(
    hass, hass_storage, cover, add_shutter, state, attributes
):
    """Keep persisted settings when load has no valid, non-restored live position."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 60)
    if state is None:
        hass.states.async_remove(cover.entity_id)
    else:
        hass.states.async_set(cover.entity_id, state, attributes)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    values = {TARGET: 60, BUFFER: 100}
    assert entry.runtime_data.values == values
    assert hass_storage[storage_key(entry.entry_id)]["data"] == {
        **values,
        ENABLED: True,
    }
    assert cover.commands == []


async def test_restart_aligns_target_without_actions(hass, cover, add_shutter):
    """Align the target and restore buffer and activation in a fresh HA instance."""
    entry = await add_shutter(cover)
    await set_enabled(hass, entry, False)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 60)
    entry_data = dict(entry.data)
    source_registry_entry = er.async_get(hass).async_get(cover.entity_id)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_stop(force=True)
    async with async_test_home_assistant(hass.loop, load_registries=True) as restarted:
        try:
            restarted.data.pop(DATA_CUSTOM_COMPONENTS)
            frame.async_setup(restarted)
            # The test helper starts with empty registries; restore the source snapshot.
            er.async_get(restarted).entities[cover.entity_id] = source_registry_entry
            assert await async_setup_component(restarted, "cover", {})
            source = SimulatedCover(position=5)
            await restarted.data["cover"].async_add_entities([source])
            restored = MockConfigEntry(
                domain=DOMAIN,
                data=entry_data,
                title=entry.title,
                unique_id=entry.unique_id,
                entry_id=entry.entry_id,
                source=SOURCE_USER,
            )
            restored.add_to_hass(restarted)
            assert await restarted.config_entries.async_setup(restored.entry_id)
            await restarted.async_start()
            await restarted.async_block_till_done()
            assert restored.runtime_data.values == {TARGET: 95, BUFFER: 100}
            assert restored.runtime_data.enabled is False
            for kind in ("switch", "binary_sensor"):
                assert (
                    restarted.states.get(
                        setting_entity_id(restarted, restored, kind, ENABLED)
                    ).state
                    == "off"
                )
            for kind in ("number", "sensor"):
                assert (
                    restarted.states.get(
                        setting_entity_id(restarted, restored, kind, TARGET)
                    ).state
                    == "95"
                )
            assert source.current_cover_position == 5
            assert source.commands == []
            assert await restarted.config_entries.async_unload(restored.entry_id)
        finally:
            await restarted.async_stop(force=True)
    assert cover.commands == []


async def test_rename_keeps_identity_and_routes_to_new_id(hass, cover, add_shutter):
    """Follow a registry rename without resetting values or issuing a command."""
    entry = await add_shutter(cover)
    unique_id = entry.unique_id
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    er.async_get(hass).async_update_entity(
        cover.entity_id, new_entity_id="cover.renamed"
    )
    await hass.async_block_till_done()
    assert entry.data[CONF_SOURCE] == "cover.renamed"
    assert entry.unique_id == unique_id
    assert setting_entity_id(hass, entry, "number", TARGET) == number_id
    assert entry.runtime_data.values[TARGET] == 30
    assert cover.commands == []
    cover.report(10, available=False)
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    cover.report(70)
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == "30"
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_SOURCE: "cover.renamed"}
    )
    assert duplicate["reason"] == "already_configured"
    await set_setting(hass, entry, TARGET, 60)
    assert cover.commands == [40]


async def test_rename_while_unloaded(hass, cover, add_shutter):
    """Align with the current position of a source renamed while tracking was off."""
    entry = await add_shutter(cover)
    assert await hass.config_entries.async_unload(entry.entry_id)
    er.async_get(hass).async_update_entity(
        cover.entity_id, new_entity_id="cover.offline_rename"
    )
    await hass.async_block_till_done()
    cover.report(10)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.data[CONF_SOURCE] == "cover.offline_rename"
    assert entry.runtime_data.values[TARGET] == 90
    assert cover.commands == []


async def test_source_removal_does_not_bind_reused_id(hass, cover, add_shutter):
    """Refuse to control or load a position from an unrelated reused entity ID."""
    entry = await add_shutter(cover)
    source_id = cover.entity_id
    er.async_get(hass).async_remove(source_id)
    await hass.async_block_till_done()
    hass.states.async_set(
        source_id, "open", {"current_position": 70, "supported_features": 4}
    )
    await set_setting(hass, entry, TARGET, 60)
    assert (
        hass.states.get(setting_entity_id(hass, entry, "number", TARGET)).state
        == STATE_UNAVAILABLE
    )
    assert entry.runtime_data.values == {TARGET: 30, BUFFER: 0}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.values == {TARGET: 30, BUFFER: 0}
    assert cover.commands == []


async def test_remove_one_mapping_and_clean_listeners(
    hass, hass_storage, cover, add_shutter
):
    """Delete only the selected mapping's entities, storage, and subscriptions."""
    other = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other])
    entry = await add_shutter(cover)
    retained = await add_shutter(other)
    controller = entry.runtime_data
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert storage_key(entry.entry_id) not in hass_storage
    assert storage_key(retained.entry_id) in hass_storage
    assert er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) == []
    assert controller._listeners == {TARGET: [], BUFFER: [], ENABLED: []}
    assert controller._unsubscribe_registry is None
    assert controller._unsubscribe_source is None
    assert controller.device_link._unsubscribe is None
    controller._async_registry_changed(None)
    controller._async_source_changed(None)
    assert controller._unsubscribe_source is None
    with pytest.raises(ServiceValidationError) as error:
        await controller.async_set_value(TARGET, 60)
    assert error.value.translation_key == "entry_unloaded"
    assert cover.commands == other.commands == []


async def test_rapid_writes_cannot_overtake(hass, cover, add_shutter):
    """Hold an older action in flight and prove later writes dispatch in order."""
    entry = await add_shutter(cover)
    cover.gate = asyncio.Event()
    first = asyncio.create_task(entry.runtime_data.async_set_value(TARGET, 20))
    await cover.command_started.wait()
    second = asyncio.create_task(entry.runtime_data.async_set_value(TARGET, 60))
    third = asyncio.create_task(entry.runtime_data.async_set_value(TARGET, 100))
    await asyncio.sleep(0)
    assert cover.commands == [80]
    assert entry.runtime_data.values[TARGET] == 20
    cover.gate.set()
    await asyncio.gather(first, second, third)
    assert cover.commands == [80, 40, 0]
    assert entry.runtime_data.values[TARGET] == 100


async def test_stop_during_save_prevents_late_command(hass, cover, add_shutter):
    """A write whose save finishes after teardown cannot send a delayed command."""
    entry = await add_shutter(cover)
    controller = entry.runtime_data
    started = asyncio.Event()
    release = asyncio.Event()
    original_save = controller.store.async_save

    async def delayed_save(data):
        """Wait for the controlled save boundary before persisting the setting."""
        started.set()
        await release.wait()
        await original_save(data)

    with patch.object(controller.store, "async_save", side_effect=delayed_save):
        write = asyncio.create_task(controller.async_set_value(TARGET, 60))
        await started.wait()
        close = asyncio.create_task(controller.async_close())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(write, close)
    assert controller.values[TARGET] == 60
    assert cover.commands == []


async def test_save_error_prevents_command(hass, cover, add_shutter):
    """A propagated persistence error leaves the old value and sends no action."""
    entry = await add_shutter(cover)
    with patch.object(
        entry.runtime_data.store, "async_save", side_effect=OSError("disk full")
    ):
        with pytest.raises(OSError):
            await set_setting(hass, entry, TARGET, 60)
    assert entry.runtime_data.values[TARGET] == 30
    assert cover.commands == []


@pytest.mark.parametrize(
    "data", [{TARGET: "nan", BUFFER: 0}, {TARGET: 50, BUFFER: 101}, {BUFFER: 0}]
)
async def test_invalid_saved_data_stops_setup(
    hass, hass_storage, cover, add_shutter, data
):
    """Reject damaged settings instead of silently commanding a fallback target."""
    entry = await add_shutter(cover)
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass_storage[storage_key(entry.entry_id)]["data"] = data
    controller = ShutterController(hass, entry)
    with pytest.raises(HomeAssistantError) as error:
        await controller.async_load()
    assert error.value.translation_key == "invalid_storage"
    assert cover.commands == []


async def test_platform_setup_failure_detaches_source_listeners(
    hass, cover, add_shutter
):
    """Clean registry and state tracking if platform forwarding raises during setup."""
    entry = await add_shutter(cover)
    assert await hass.config_entries.async_unload(entry.entry_id)
    from custom_components.natural_shutter import async_setup_entry

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(side_effect=HomeAssistantError("setup failed")),
    ):
        with pytest.raises(HomeAssistantError):
            await async_setup_entry(hass, entry)
    assert entry.runtime_data._unsubscribe_registry is None
    assert entry.runtime_data._unsubscribe_source is None
    assert entry.runtime_data.device_link._unsubscribe is None
    assert cover.commands == []


async def test_context_passed_to_cover_action(hass, cover, add_shutter):
    """Carry the explicit number action's context into the delegated cover action."""
    entry = await add_shutter(cover)
    context = Context()
    calls = []

    def observe(event):
        """Capture cover service contexts without changing any entity."""
        if event.data["domain"] == "cover":
            calls.append(event.context)

    remove = hass.bus.async_listen("call_service", observe)
    try:
        await hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": setting_entity_id(hass, entry, "number", TARGET),
                "value": 60,
            },
            blocking=True,
            context=context,
        )
        await hass.async_block_till_done()
    finally:
        remove()
    assert calls == [context]
    assert cover.commands == [40]


async def test_failed_platform_unload_keeps_mapping_active(hass, cover, add_shutter):
    """Retain a working controller if HA cannot unload its entity platforms."""
    from custom_components.natural_shutter import async_unload_entry

    entry = await add_shutter(cover)
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await async_unload_entry(hass, entry)
    assert entry.runtime_data._unsubscribe_registry is not None
    assert len(entry.runtime_data._listeners[TARGET]) == 2
    assert cover.commands == []
