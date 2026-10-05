"""Verify command Activity and suppression notifications without hardware."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.core import Context
from homeassistant.data_entry_flow import InvalidData
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.natural_shutter.const import (
    BUFFER,
    CONF_NOTIFICATION_SERVICE,
    CONF_SOURCE,
    DOMAIN,
    TARGET,
)

from .conftest import SimulatedCover, select_phone, set_setting, setting_entity_id


@pytest.mark.parametrize("language", ["de", "en"])
async def test_suppression_message_values_and_local_time(
    hass, cover, add_shutter, phone, activity_events, freezer, language
):
    """Publish identical localized snapshots to Activity and the chosen phone."""
    hass.config.language = language
    await hass.config.async_set_time_zone("Europe/Berlin")
    entry = await add_shutter(cover, "Wohnzimmer")
    await select_phone(hass, entry)
    await set_setting(hass, entry, BUFFER, 10)
    cover.report(35)
    freezer.move_to("2026-10-05 12:34:56+00:00")
    await set_setting(hass, entry, TARGET, 70)
    assert cover.commands == []
    assert len(activity_events) == phone.call_count == 1
    event = activity_events[0]
    assert event.data["domain"] == DOMAIN
    assert event.data["entity_id"] == setting_entity_id(hass, entry, "number", TARGET)
    if language == "de":
        title = "Wohnzimmer: Keine Fahrt"
        message = (
            "2026-10-05 14:34:56+02:00 · cover.living_room: Abstand kleiner als Puffer. "
            "Ziel 30 → 70 %, Ist 65 % (HA 35 %), HA-Ziel 30 %, Abstand 5 pp, Puffer 10 pp."
        )
    else:
        title = "Wohnzimmer: No movement"
        message = (
            "2026-10-05 14:34:56+02:00 · cover.living_room: Difference below buffer. "
            "Target 30 → 70 %, actual 65 % (HA 35 %), HA target 30 %, difference 5 pp, buffer 10 pp."
        )
    assert event.data["name"] == title
    assert event.data["message"] == message
    call = phone.call_args.args[0]
    assert call.data == {"title": title, "message": message}
    assert call.context is event.context


@pytest.mark.parametrize(
    "actual, buffer, target, suppressed",
    [
        (35, 10, 70, True),
        (30, 0, 70, True),
        (40, 10, 70, False),
        (20, 10, 70, False),
        (30.1, 0, 70, False),
        (0, 100, 0, False),
        (100, 0, 0, True),
        (95, 10, 0, True),
        (5, 10, 100, True),
        (35.5, 10, 70, True),
    ],
)
async def test_position_decisions_only_notify_on_suppression(
    hass, cover, add_shutter, phone, activity_events, actual, buffer, target, suppressed
):
    """Log every valid changed target, only pushing strict rule suppressions."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    await set_setting(hass, entry, BUFFER, buffer)
    cover.report(actual)
    await set_setting(hass, entry, TARGET, target)
    assert len(activity_events) == 1
    assert phone.call_count == int(suppressed)
    assert cover.commands == ([] if suppressed else [100 - target])
    message = activity_events[0].data["message"]
    reason = (
        (
            "Already at the requested position"
            if actual == 100 - target
            else "Difference below buffer"
        )
        if suppressed
        else "Position command sent to source cover"
    )
    assert reason in message
    assert f"difference {abs(actual - (100 - target)):g} pp" in message


@pytest.mark.parametrize("language", ["de", "en"])
async def test_successful_command_activity_values_without_push(
    hass, cover, add_shutter, phone, activity_events, freezer, language
):
    """Log command snapshots in HA's language and time zone without phone calls."""
    hass.config.language = language
    await hass.config.async_set_time_zone("Europe/Berlin")
    entry = await add_shutter(cover, "Wohnzimmer")
    await select_phone(hass, entry)
    await set_setting(hass, entry, BUFFER, 10)
    freezer.move_to("2026-10-05 12:34:56+00:00")
    await set_setting(hass, entry, TARGET, 70)
    assert cover.commands == [30]
    assert len(activity_events) == 1
    event = activity_events[0]
    if language == "de":
        title = "Wohnzimmer: Fahrbefehl gesendet"
        message = (
            "2026-10-05 14:34:56+02:00 · cover.living_room: Fahrbefehl an Quell-Rollladen gesendet. "
            "Ziel 30 → 70 %, Ist 30 % (HA 70 %), HA-Ziel 30 %, Abstand 40 pp, Puffer 10 pp."
        )
    else:
        title = "Wohnzimmer: Position command sent"
        message = (
            "2026-10-05 14:34:56+02:00 · cover.living_room: Position command sent to source cover. "
            "Target 30 → 70 %, actual 30 % (HA 70 %), HA target 30 %, difference 40 pp, buffer 10 pp."
        )
    assert event.data == {
        "name": title,
        "message": message,
        "domain": DOMAIN,
        "entity_id": setting_entity_id(hass, entry, "number", TARGET),
    }
    phone.assert_not_called()


async def test_command_logs_after_success_with_position_before_dispatch(
    hass, cover, add_shutter, phone, activity_events
):
    """Wait for command success while retaining the position used in the decision."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    cover.gate = asyncio.Event()
    write = asyncio.create_task(set_setting(hass, entry, TARGET, 70))
    try:
        await cover.command_started.wait()
        assert activity_events == []
        cover.report(30)
    finally:
        cover.gate.set()
        await write
    assert len(activity_events) == 1
    assert "actual 30 % (HA 70 %)" in activity_events[0].data["message"]
    assert "difference 40 pp, buffer 0 pp" in activity_events[0].data["message"]
    assert cover.commands == [30]
    phone.assert_not_called()


async def test_default_is_activity_without_push(
    hass, cover, add_shutter, phone, activity_events
):
    """Keep phone notifications opt-in while always recording suppression."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    assert len(activity_events) == 1
    phone.assert_not_called()
    assert entry.runtime_data.values == {TARGET: 70, BUFFER: 100}
    assert cover.commands == []


async def test_options_enable_switch_and_disable_without_alignment(
    hass, cover, add_shutter, phone, activity_events
):
    """Change recipients immediately without resetting targets or moving covers."""
    other_phone = AsyncMock()
    hass.services.async_register("notify", "mobile_app_other_phone", other_phone)
    entry = await add_shutter(cover)
    controller = entry.runtime_data
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    for service, target in [
        ("mobile_app_test_phone", 71),
        ("mobile_app_other_phone", 72),
        ("", 73),
    ]:
        old_values = dict(controller.values)
        await select_phone(hass, entry, service)
        assert entry.runtime_data is controller
        assert controller.values == old_values
        await set_setting(hass, entry, TARGET, target)
    assert len(activity_events) == 4
    assert phone.call_count == other_phone.call_count == 1
    assert "70 → 71" in phone.call_args.args[0].data["message"]
    assert "71 → 72" in other_phone.call_args.args[0].data["message"]
    assert cover.commands == []


async def test_options_list_only_companion_app_services(
    hass, cover, add_shutter, phone
):
    """Offer a localized off choice and phones while excluding other services."""
    hass.config.language = "de"
    hass.services.async_register("notify", "email", AsyncMock())
    entry = await add_shutter(cover)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    selector = form["data_schema"].schema[CONF_NOTIFICATION_SERVICE]
    assert selector.config["options"] == [
        {"value": "", "label": "Push-Nachrichten deaktiviert"},
        {"value": "mobile_app_test_phone", "label": "notify.mobile_app_test_phone"},
    ]
    assert selector("") == ""
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            form["flow_id"], {CONF_NOTIFICATION_SERVICE: "email"}
        )
    assert cover.commands == []


async def test_no_phones_and_removed_phone_can_be_disabled(hass, cover, add_shutter):
    """Allow notification opt-out with no phones or a stale selected service."""
    entry = await add_shutter(cover)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    selector = form["data_schema"].schema[CONF_NOTIFICATION_SERVICE]
    assert len(selector.config["options"]) == 1
    await select_phone(hass, entry, "")
    hass.config_entries.async_update_entry(
        entry, options={CONF_NOTIFICATION_SERVICE: "mobile_app_removed"}
    )
    form = await hass.config_entries.options.async_init(entry.entry_id)
    selector = form["data_schema"].schema[CONF_NOTIFICATION_SERVICE]
    assert selector.config["options"][-1] == {
        "value": "mobile_app_removed",
        "label": "notify.mobile_app_removed (unavailable)",
    }
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_NOTIFICATION_SERVICE: "mobile_app_removed"}
    )
    assert result["errors"] == {
        CONF_NOTIFICATION_SERVICE: "notification_service_unavailable"
    }
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_NOTIFICATION_SERVICE: ""}
    )
    assert result["type"] == "create_entry"
    assert cover.commands == []


@pytest.mark.parametrize("service", ["mobile_app_removed", "email"])
async def test_missing_or_invalid_notifier_keeps_activity(
    hass, cover, add_shutter, activity_events, caplog, service
):
    """Retain the saved target and diagnostic if a notifier becomes unusable."""
    entry = await add_shutter(cover)
    hass.config_entries.async_update_entry(
        entry, options={CONF_NOTIFICATION_SERVICE: service}
    )
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    assert len(activity_events) == 1
    assert "notification service is unavailable" in caplog.text
    assert entry.runtime_data.values[TARGET] == 70
    assert cover.commands == []


@pytest.mark.parametrize("error", [HomeAssistantError("Push failed"), TimeoutError()])
async def test_push_failure_does_not_fail_target_write(
    hass, cover, add_shutter, phone, activity_events, caplog, error
):
    """Preserve suppression and Activity when the simulated phone service fails."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    phone.side_effect = error
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    assert len(activity_events) == 1
    assert "the Activity entry was recorded" in caplog.text
    assert entry.runtime_data.values[TARGET] == 70
    assert cover.commands == []


@pytest.mark.parametrize("suppressed", [True, False])
async def test_activity_follows_target_rename_and_action_context(
    hass, cover, add_shutter, phone, activity_events, suppressed
):
    """Associate diagnostics with the renamed integration entity and action."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    registry = er.async_get(hass)
    registry.async_update_entity(
        setting_entity_id(hass, entry, "number", TARGET),
        new_entity_id="number.renamed_shutter_target",
    )
    await hass.async_block_till_done()
    await set_setting(hass, entry, BUFFER, 100 if suppressed else 0)
    context = Context()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.renamed_shutter_target", "value": 70},
        blocking=True,
        context=context,
    )
    await hass.async_block_till_done()
    assert activity_events[0].data["entity_id"] == "number.renamed_shutter_target"
    assert activity_events[0].context is context
    if suppressed:
        assert phone.call_args.args[0].context is context
    else:
        phone.assert_not_called()
    assert cover.commands == ([] if suppressed else [30])


async def test_excluded_events_do_not_create_diagnostics(
    hass, cover, add_shutter, phone, activity_events
):
    """Ignore setup, same targets, external reports, buffer writes, and reload."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    cover.report(10)
    await set_setting(hass, entry, TARGET, 30.4)
    await set_setting(hass, entry, BUFFER, 100)
    cover.report(10, available=False)
    await hass.async_block_till_done()
    await set_setting(hass, entry, TARGET, 70)
    cover.report(10)
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.options[CONF_NOTIFICATION_SERVICE] == "mobile_app_test_phone"
    assert entry.runtime_data.values == {TARGET: 90, BUFFER: 100}
    assert activity_events == []
    phone.assert_not_called()
    assert cover.commands == []


@pytest.mark.parametrize("failure", ["invalid_position", "command_failed"])
async def test_action_errors_do_not_log_success_or_notify(
    hass, cover, add_shutter, phone, activity_events, failure
):
    """Keep validation of accepted writes and command failures outside Activity."""
    entry = await add_shutter(cover)
    await select_phone(hass, entry)
    if failure == "invalid_position":
        cover.report(None)
    else:
        cover.fail = True
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_set_value(TARGET, 70)
    assert activity_events == []
    phone.assert_not_called()


async def test_reconfigure_keeps_recipient_and_independent_mappings(
    hass, cover, add_shutter, phone, activity_events
):
    """Retain options on source replacement and route diagnostics per mapping."""
    first = await add_shutter(cover)
    await select_phone(hass, first)
    replacement = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([replacement])
    await set_setting(hass, first, BUFFER, 100)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": first.entry_id},
        data={CONF_SOURCE: replacement.entity_id},
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert first.options[CONF_NOTIFICATION_SERVICE] == "mobile_app_test_phone"
    second = await add_shutter(cover)
    await set_setting(hass, second, BUFFER, 100)
    await set_setting(hass, first, TARGET, 70)
    await set_setting(hass, second, TARGET, 80)
    assert len(activity_events) == 2
    assert phone.call_count == 1
    assert replacement.entity_id in phone.call_args.args[0].data["message"]
    assert cover.commands == replacement.commands == []
