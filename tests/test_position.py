"""Verify passive final-position alignment and unknown-position availability."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.data_entry_flow import InvalidData
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from custom_components.natural_shutter.const import (
    BUFFER,
    CONF_NOTIFICATION_SERVICE,
    CONF_POSITION_QUIET_SECONDS,
    TARGET,
    storage_key,
)

from .conftest import (
    SimulatedCover,
    advance_time,
    select_phone,
    set_setting,
    setting_entity_id,
)


@pytest.mark.parametrize("motion", ["opening", "closing"])
async def test_align_after_reported_stop(
    hass, hass_storage, cover, add_shutter, phone, activity_events, motion
):
    """Keep a requested target during motion and align the final position silently."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    requested = 20 if motion == "opening" else 80
    final = 75 if motion == "opening" else 45
    await set_setting(hass, entry, TARGET, requested)
    activity_events.clear()
    cover.report(final, motion=motion)
    await hass.async_block_till_done()
    await advance_time(hass, 60)
    assert entry.runtime_data.values[TARGET] == requested
    cover.report(final, motion=motion)
    await hass.async_block_till_done()
    cover.report(final)
    await hass.async_block_till_done()
    await advance_time(hass, 0.5)
    assert entry.runtime_data.values[TARGET] == requested
    await advance_time(hass, 3)
    assert entry.runtime_data.values[TARGET] == 100 - final
    assert hass_storage[storage_key(entry.entry_id)]["data"] == {
        TARGET: 100 - final,
        BUFFER: 0,
    }
    for kind in ("number", "sensor"):
        assert hass.states.get(
            setting_entity_id(hass, entry, kind, TARGET)
        ).state == str(100 - final)
    assert cover.commands == [100 - requested]
    assert activity_events == []
    phone.assert_not_called()


async def test_quiet_time_and_late_final_report(hass, cover, add_shutter):
    """Use the latest position and invalidate an earlier timer without motion flags."""
    entry = await add_shutter(cover)
    tracker = entry.runtime_data.position_tracker
    with patch(
        "custom_components.natural_shutter.position.async_call_later",
        wraps=async_call_later,
    ) as schedule:
        cover.report(50)
        await hass.async_block_till_done()
        first = schedule.call_args.args[2]
        assert schedule.call_args.args[1] == 10
        cover.report(42.5)
        await hass.async_block_till_done()
        await first(dt_util.utcnow())
        assert entry.runtime_data.values[TARGET] == 30
        revision = tracker.revision
        hass.states.async_set(
            cover.entity_id,
            "open",
            {
                **hass.states.get(cover.entity_id).attributes,
                "extra": "unchanged position",
            },
        )
        await hass.async_block_till_done()
        assert tracker.revision == revision
        assert schedule.call_count == 2
    await advance_time(hass, 8)
    assert entry.runtime_data.values[TARGET] == 30
    await advance_time(hass, 11)
    assert entry.runtime_data.values[TARGET] == 58
    assert cover.commands == []


async def test_late_report_after_stop_restarts_grace(hass, cover, add_shutter):
    """Include delayed final position reports after the source signals stopped."""
    entry = await add_shutter(cover)
    cover.report(60, motion="closing")
    await hass.async_block_till_done()
    cover.report(50)
    await hass.async_block_till_done()
    cover.report(42)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.runtime_data.values[TARGET] == 58
    assert cover.commands == []


async def test_explicit_target_discards_previous_feedback(hass, cover, add_shutter):
    """A new target wins over a queued alignment, including a callback already ready."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    with patch(
        "custom_components.natural_shutter.position.async_call_later",
        wraps=async_call_later,
    ) as schedule:
        cover.report(50)
        await hass.async_block_till_done()
        old_callback = schedule.call_args.args[2]
        await set_setting(hass, entry, TARGET, 80)
        await old_callback(dt_util.utcnow())
    await advance_time(hass, 20)
    assert entry.runtime_data.values[TARGET] == 80
    cover.report(50)
    await hass.async_block_till_done()
    await advance_time(hass, 20)
    assert entry.runtime_data.values[TARGET] == 80
    cover.report(40, motion="closing")
    await hass.async_block_till_done()
    await set_setting(hass, entry, TARGET, 70)
    cover.report(35)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.runtime_data.values[TARGET] == 65
    assert cover.commands == []


async def test_load_during_motion_defers_alignment(hass, cover, add_shutter):
    """Reload a moving source without replacing a saved target with an intermediate."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 60)
    cover.report(40, motion="closing")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.values[TARGET] == 60
    await advance_time(hass, 60)
    assert entry.runtime_data.values[TARGET] == 60
    cover.report(20)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.runtime_data.values == {TARGET: 80, BUFFER: 100}
    assert cover.commands == []


@pytest.mark.parametrize("invalid", [None, "nan", -1, 101])
async def test_invalid_position_hides_target_and_cancels_alignment(
    hass, cover, add_shutter, invalid
):
    """Keep history but expose no editable target until a valid position returns."""
    entry = await add_shutter(cover)
    cover.report(40)
    await hass.async_block_till_done()
    cover.report(invalid)
    await hass.async_block_till_done()
    await advance_time(hass, 20)
    target_id = setting_entity_id(hass, entry, "number", TARGET)
    assert hass.states.get(target_id).state == STATE_UNAVAILABLE
    assert (
        hass.states.get(setting_entity_id(hass, entry, "sensor", TARGET)).state == "30"
    )
    assert (
        hass.states.get(setting_entity_id(hass, entry, "number", BUFFER)).state == "0"
    )
    await set_setting(hass, entry, TARGET, 60)
    assert entry.runtime_data.values[TARGET] == 30
    cover.report(20)
    await hass.async_block_till_done()
    assert hass.states.get(target_id).state != STATE_UNAVAILABLE
    await advance_time(hass, 11)
    assert entry.runtime_data.values[TARGET] == 80
    assert cover.commands == []


async def test_outage_during_motion_waits_for_valid_stop(hass, cover, add_shutter):
    """Resume unfinished motion after an outage without aligning an invalid sample."""
    entry = await add_shutter(cover)
    cover.report(40, motion="closing")
    await hass.async_block_till_done()
    cover.report(40, available=False)
    await hass.async_block_till_done()
    await advance_time(hass, 20)
    cover.report(40)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.runtime_data.values[TARGET] == 60
    assert cover.commands == []


@pytest.mark.parametrize("invalidate", ["remove", "unload"])
async def test_source_loss_or_unload_cancels_alignment(
    hass, cover, add_shutter, invalidate
):
    """Detach timers and reject late callbacks after source removal or entry unload."""
    entry = await add_shutter(cover)
    controller = entry.runtime_data
    with patch(
        "custom_components.natural_shutter.position.async_call_later",
        wraps=async_call_later,
    ) as schedule:
        cover.report(40)
        await hass.async_block_till_done()
        old_callback = schedule.call_args.args[2]
        if invalidate == "remove":
            er.async_get(hass).async_remove(cover.entity_id)
        else:
            assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        await old_callback(dt_util.utcnow())
    await advance_time(hass, 20)
    assert controller.values[TARGET] == 30
    if invalidate == "remove":
        assert await hass.config_entries.async_unload(entry.entry_id)
    assert controller.position_tracker._cancel_timer is None
    assert cover.commands == []


async def test_rename_preserves_pending_alignment(hass, cover, add_shutter):
    """Follow a registry rename without losing a real position change awaiting alignment."""
    entry = await add_shutter(cover)
    cover.report(50)
    await hass.async_block_till_done()
    er.async_get(hass).async_update_entity(
        cover.entity_id, new_entity_id="cover.renamed"
    )
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert entry.runtime_data.values[TARGET] == 50
    assert cover.commands == []


async def test_burst_reports_keep_movement_evidence(hass, cover, add_shutter):
    """Recognize a reported stop even when several events precede their callbacks."""
    entry = await add_shutter(cover)
    cover.report(60, motion="closing")
    cover.report(50)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.runtime_data.values[TARGET] == 50
    assert cover.commands == []


async def test_stationary_source_preserves_buffered_target(hass, cover, add_shutter):
    """Leave a suppressed target unchanged without actual position changes."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    cover.report(70)
    await hass.async_block_till_done()
    cover.report(70, motion="closing")
    await hass.async_block_till_done()
    cover.report(70)
    await hass.async_block_till_done()
    await advance_time(hass, 20)
    assert entry.runtime_data.values == {TARGET: 70, BUFFER: 100}
    assert cover.commands == []


async def test_alignment_save_failure_preserves_target(
    hass, hass_storage, cover, add_shutter, caplog, activity_events
):
    """Keep memory and storage on failure and align a later changed position normally."""
    entry = await add_shutter(cover)
    cover.report(40)
    await hass.async_block_till_done()
    with patch.object(
        entry.runtime_data.store, "async_save", side_effect=OSError("full")
    ):
        await advance_time(hass, 11)
    assert entry.runtime_data.values[TARGET] == 30
    assert hass_storage[storage_key(entry.entry_id)]["data"][TARGET] == 30
    assert "Cannot align target" in caplog.text
    assert activity_events == []
    cover.report(30)
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert entry.runtime_data.values[TARGET] == 70
    assert len(activity_events) == 1
    assert cover.commands == []


@pytest.mark.parametrize("invalidate", ["moving", "unavailable", "unload"])
async def test_changed_source_during_alignment_save_is_not_published(
    hass, hass_storage, cover, add_shutter, invalidate, activity_events
):
    """Undo a stale persisted alignment when motion, outage, or teardown occurs in flight."""
    entry = await add_shutter(cover)
    controller = entry.runtime_data
    cover.report(40)
    await hass.async_block_till_done()
    started = asyncio.Event()
    release = asyncio.Event()
    original_save = controller.store.async_save

    async def delayed_save(data):
        """Pause only the candidate alignment and allow the corrective save to finish."""
        if data[TARGET] == 60:
            started.set()
            await release.wait()
        await original_save(data)

    with patch.object(controller.store, "async_save", side_effect=delayed_save):
        write = asyncio.create_task(
            controller.async_align_target(controller.position_tracker.revision, 40)
        )
        await started.wait()
        if invalidate == "unload":
            controller.async_stop()
        else:
            cover.report(40, available=invalidate != "unavailable", motion="closing")
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        release.set()
        await write
    assert controller.values[TARGET] == 30
    assert hass_storage[storage_key(entry.entry_id)]["data"][TARGET] == 30
    assert activity_events == []
    assert cover.commands == []


async def test_quiet_time_options_and_independent_mappings(hass, cover, add_shutter):
    """Persist per-entry quiet timing and leave another entry's synchronization independent."""
    other = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other])
    first = await add_shutter(cover)
    second = await add_shutter(other)
    form = await hass.config_entries.options.async_init(first.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {CONF_NOTIFICATION_SERVICE: "", CONF_POSITION_QUIET_SECONDS: 30},
    )
    assert result["type"] == "create_entry"
    assert first.options[CONF_POSITION_QUIET_SECONDS] == 30
    cover.report(40)
    other.report(20)
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert first.runtime_data.values[TARGET] == 30
    assert second.runtime_data.values[TARGET] == 80
    await advance_time(hass, 31)
    assert first.runtime_data.values[TARGET] == 60
    assert cover.commands == other.commands == []


@pytest.mark.parametrize("seconds", [0, -1, 301])
async def test_invalid_quiet_time_rejected(hass, cover, add_shutter, seconds):
    """Reject quiet intervals outside the documented one-to-300-second range."""
    entry = await add_shutter(cover)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            form["flow_id"],
            {CONF_NOTIFICATION_SERVICE: "", CONF_POSITION_QUIET_SECONDS: seconds},
        )
