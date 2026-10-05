"""Verify external target-alignment Activity and attribution of own movement."""

from unittest.mock import patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.natural_shutter.const import (
    BUFFER,
    DATA_POSITION_COMMANDS,
    DOMAIN,
    TARGET,
)

from .conftest import (
    SimulatedCover,
    advance_time,
    select_phone,
    set_setting,
    setting_entity_id,
)


@pytest.mark.parametrize("language", ["de", "en"])
async def test_external_alignment_activity_values(
    hass, cover, add_shutter, phone, activity_events, freezer, language
):
    """Log one localized persisted change on the renamed target, without phone push."""
    hass.config.language = language
    await hass.config.async_set_time_zone("Europe/Berlin")
    entry = await add_shutter(cover, "Wohnzimmer")
    await select_phone(hass, entry)
    await set_setting(hass, entry, BUFFER, 12)
    er.async_get(hass).async_update_entity(
        setting_entity_id(hass, entry, "number", TARGET),
        new_entity_id="number.renamed_target",
    )
    await hass.async_block_till_done()
    freezer.move_to("2026-10-05 12:34:56+00:00")
    context = Context()
    cover.report(60, motion="closing", context=context)
    await hass.async_block_till_done()
    assert activity_events == []
    cover.report(42.5, context=context)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.runtime_data.values == {TARGET: 58, BUFFER: 12}
    assert len(activity_events) == 1
    event = activity_events[0]
    assert event.context is context
    assert event.data["domain"] == DOMAIN
    assert event.data["entity_id"] == "number.renamed_target"
    if language == "de":
        assert event.data["name"] == "Wohnzimmer: Zielwert aktualisiert"
        assert event.data["message"] == (
            "2026-10-05 14:34:56+02:00 · cover.living_room: "
            "Zielwert nach externer Positionsänderung aktualisiert. "
            "Ziel 30 → 58 %, Ist 57.5 % (HA 42.5 %). "
            "Natural Shutter hat für diese Änderung keinen Fahrbefehl gesendet."
        )
    else:
        assert event.data["name"] == "Wohnzimmer: Target updated"
        assert event.data["message"] == (
            "2026-10-05 14:34:56+02:00 · cover.living_room: "
            "Target updated after an external position change. "
            "Target 30 → 58 %, actual 57.5 % (HA 42.5 %). "
            "Natural Shutter did not send a movement command for this change."
        )
    cover.report(42.4, context=context)
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert len(activity_events) == 1
    assert cover.commands == []
    phone.assert_not_called()


@pytest.mark.parametrize(
    "feedback", ["motion", "quiet", "child", "no_context", "reload"]
)
async def test_own_feedback_has_no_external_entry(
    hass, cover, add_shutter, phone, activity_events, feedback
):
    """Keep own feedback quiet, then log a subsequent unrelated position change."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    await set_setting(hass, entry, TARGET, 80)
    activity_events.clear()
    command = hass.data[DATA_POSITION_COMMANDS][entry.entry_id]
    context = (
        Context(parent_id=command.context.id)
        if feedback == "child"
        else Context()
        if feedback == "no_context"
        else command.context
    )
    if feedback != "quiet":
        cover.report(60, motion="closing", context=context)
        await hass.async_block_till_done()
    if feedback == "reload":
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    cover.report(45, context=context)
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert entry.runtime_data.values[TARGET] == 55
    assert activity_events == []
    assert entry.entry_id not in hass.data[DATA_POSITION_COMMANDS]
    cover.report(40, context=Context())
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert len(activity_events) == 1
    assert "Target 55 → 60" in activity_events[0].data["message"]
    assert cover.commands == [20]
    phone.assert_not_called()


@pytest.mark.parametrize(
    "interruption", ["user", "automation", "reverse", "outside", "expired", "failed"]
)
async def test_external_change_overrides_own_attribution(
    hass, cover, add_shutter, activity_events, interruption
):
    """Log identifiable external movement instead of retaining a stale own command."""
    entry = await add_shutter(cover)
    if interruption == "failed":
        cover.fail = True
        with pytest.raises(HomeAssistantError):
            await set_setting(hass, entry, TARGET, 80)
    else:
        await set_setting(hass, entry, TARGET, 80)
    activity_events.clear()
    position = 85 if interruption == "outside" else 45
    context = (
        Context(user_id="external-user")
        if interruption == "user"
        else Context(parent_id="external-automation")
        if interruption == "automation"
        else Context()
    )
    if interruption == "expired":
        command = hass.data[DATA_POSITION_COMMANDS][entry.entry_id]
        with patch(
            "custom_components.natural_shutter.position.monotonic",
            return_value=command.expires + 1,
        ):
            cover.report(position, context=context)
            await hass.async_block_till_done()
    else:
        cover.report(
            position,
            motion="opening" if interruption == "reverse" else None,
            context=context,
        )
        await hass.async_block_till_done()
        if interruption == "reverse":
            cover.report(position, context=context)
            await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert entry.runtime_data.values[TARGET] == 100 - position
    assert len(activity_events) == 1
    assert "external position change" in activity_events[0].data["message"]
    assert cover.commands == [20]


async def test_attribution_is_independent_and_removed_with_entry(
    hass, cover, add_shutter, activity_events
):
    """Keep own command origin scoped to its entry and remove it with the mapping."""
    other = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other])
    first = await add_shutter(cover)
    second = await add_shutter(other)
    await set_setting(hass, first, TARGET, 80)
    activity_events.clear()
    cover.report(45, context=Context())
    other.report(20)
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert len(activity_events) == 1
    assert activity_events[0].data["entity_id"] == setting_entity_id(
        hass, second, "number", TARGET
    )
    await set_setting(hass, first, TARGET, 70)
    assert first.entry_id in hass.data[DATA_POSITION_COMMANDS]
    assert await hass.config_entries.async_remove(first.entry_id)
    assert first.entry_id not in hass.data[DATA_POSITION_COMMANDS]
    assert other.commands == []


async def test_stop_without_position_change_ends_own_attribution(
    hass, cover, add_shutter, activity_events
):
    """A stopped but unmoved own command must not silence the next external movement."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, TARGET, 80)
    activity_events.clear()
    cover.report(70, motion="closing")
    await hass.async_block_till_done()
    cover.report(70)
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.entry_id not in hass.data[DATA_POSITION_COMMANDS]
    assert entry.runtime_data.values[TARGET] == 80
    cover.report(45, context=Context())
    await hass.async_block_till_done()
    await advance_time(hass, 11)
    assert len(activity_events) == 1
    assert "Target 80 → 55" in activity_events[0].data["message"]


async def test_first_final_position_after_stop_keeps_own_origin(
    hass, cover, add_shutter, activity_events
):
    """Accept a first changed position during the stop grace period as own feedback."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, TARGET, 80)
    activity_events.clear()
    cover.report(70, motion="closing")
    await hass.async_block_till_done()
    cover.report(70)
    await hass.async_block_till_done()
    await advance_time(hass, 0.5)
    cover.report(45, context=Context())
    await hass.async_block_till_done()
    await advance_time(hass, 3)
    assert entry.runtime_data.values[TARGET] == 55
    assert activity_events == []
    assert cover.commands == [20]
