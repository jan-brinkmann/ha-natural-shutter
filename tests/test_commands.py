"""Check conversion, buffer boundaries, validation, and command exclusions."""

import math
from unittest.mock import patch

import pytest
from homeassistant.components.cover import ATTR_CURRENT_POSITION, CoverEntityFeature
from homeassistant.const import (
    ATTR_RESTORED,
    ATTR_SUPPORTED_FEATURES,
    STATE_UNAVAILABLE,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.natural_shutter.const import BUFFER, TARGET, storage_key
from custom_components.natural_shutter.source import (
    normalize_percentage,
    valid_percentage,
)

from .conftest import SimulatedCover, advance_time, set_setting, setting_entity_id


@pytest.mark.parametrize(
    "target, ha_target", [(0, 100), (25, 75), (50, 50), (75, 25), (100, 0)]
)
async def test_conversion(hass, cover, add_shutter, target, ha_target):
    """Invert each explicit target exactly once through HA's cover service."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, TARGET, target)
    assert cover.commands == [ha_target]


@pytest.mark.parametrize(
    "actual, buffer, target, expected",
    [
        (45, 10, 70, [30]),
        (40, 10, 70, [30]),
        (35, 10, 70, []),
        (30, 10, 70, []),
        (20, 10, 70, [30]),
        (15, 10, 70, [30]),
        (30, 0, 70, []),
        (30.1, 0, 70, [30]),
        (29.9, 0, 70, [30]),
        (0, 100, 0, [100]),
        (100, 100, 100, [0]),
        (50, 100, 0, []),
        (50, 100, 100, []),
        (95, 10, 0, []),
        (5, 10, 100, []),
        (100, 0, 0, []),
        (0, 0, 100, []),
    ],
)
async def test_buffer_algorithm(
    hass, hass_storage, cover, add_shutter, actual, buffer, target, expected
):
    """Apply an inclusive minimum deviation on both sides, including endpoints."""
    entry = await add_shutter(cover)
    cover.report(actual)
    await set_setting(hass, entry, BUFFER, buffer)
    assert cover.commands == []
    await set_setting(hass, entry, TARGET, target)
    assert cover.commands == expected
    assert entry.runtime_data.values[TARGET] == target
    assert hass_storage[storage_key(entry.entry_id)]["data"] == {
        TARGET: target,
        BUFFER: buffer,
    }


async def test_unchanged_normalized_target(hass, cover, add_shutter):
    """An unchanged normalized target never sends a command or sensor event."""
    entry = await add_shutter(cover)
    sensor_id = setting_entity_id(hass, entry, "sensor", TARGET)
    previous_state = hass.states.get(sensor_id)
    cover.report(10)
    await set_setting(hass, entry, TARGET, 30)
    await set_setting(hass, entry, TARGET, 30.4)
    assert entry.runtime_data.values[TARGET] == 30
    assert hass.states.get(sensor_id) is previous_state
    assert cover.commands == []


async def test_buffer_and_external_changes_never_recheck(hass, cover, add_shutter):
    """Align changed source positions without replaying an earlier suppressed target."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    await set_setting(hass, entry, BUFFER, 0)
    for position in (0, 15, 30, 45, 100):
        cover.report(position)
        await hass.async_block_till_done()
        assert entry.runtime_data.values == {TARGET: 70, BUFFER: 0}
    await advance_time(hass, 11)
    assert entry.runtime_data.values == {TARGET: 0, BUFFER: 0}
    assert cover.commands == []


@pytest.mark.parametrize("key", [TARGET, BUFFER])
@pytest.mark.parametrize(
    "value", [-1, 101, math.nan, math.inf, -math.inf, True, None, "bad"]
)
async def test_invalid_setting(hass, cover, add_shutter, key, value):
    """Reject invalid writes without changing settings or dispatching a command."""
    entry = await add_shutter(cover)
    with pytest.raises(ServiceValidationError) as error:
        await entry.runtime_data.async_set_value(key, value)
    assert error.value.translation_key == "invalid_percentage"
    assert entry.runtime_data.values == {TARGET: 30, BUFFER: 0}
    assert cover.commands == []


@pytest.mark.parametrize("value", [None, "nan", "inf", -1, 101, True, "bad"])
async def test_invalid_actual_position(hass, cover, add_shutter, value, caplog):
    """Make an invalid position unavailable and skip target actions without saving."""
    entry = await add_shutter(cover)
    cover.report(value)
    await hass.async_block_till_done()
    assert (
        hass.states.get(setting_entity_id(hass, entry, "number", TARGET)).state
        == STATE_UNAVAILABLE
    )
    await set_setting(hass, entry, TARGET, 60)
    assert entry.runtime_data.values[TARGET] == 30
    assert "not currently available" in caplog.text
    cover.report(70)
    await hass.async_block_till_done()
    await set_setting(hass, entry, TARGET, 30)
    assert cover.commands == []


@pytest.mark.parametrize("state", ["unknown", "unavailable"])
async def test_unavailable_target_is_not_replayed(
    hass, hass_storage, cover, add_shutter, state
):
    """Offline actions are skipped and never saved or replayed after reconnection."""
    entry = await add_shutter(cover)
    hass.states.async_set(
        cover.entity_id,
        state,
        {
            ATTR_CURRENT_POSITION: 70,
            ATTR_SUPPORTED_FEATURES: CoverEntityFeature.SET_POSITION,
        },
    )
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    await set_setting(hass, entry, TARGET, 60)
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    assert hass_storage[storage_key(entry.entry_id)]["data"][TARGET] == 30
    cover.report(70)
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == "30"
    await set_setting(hass, entry, TARGET, 30)
    assert cover.commands == []
    await set_setting(hass, entry, TARGET, 61)
    assert cover.commands == [39]


async def test_restored_source_is_not_a_live_position(hass, cover, add_shutter):
    """Hide the target for restored source placeholders with a valid numeric position."""
    entry = await add_shutter(cover)
    hass.states.async_set(
        cover.entity_id,
        "open",
        {ATTR_RESTORED: True, ATTR_CURRENT_POSITION: 70, ATTR_SUPPORTED_FEATURES: 4},
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get(setting_entity_id(hass, entry, "number", TARGET)).state
        == STATE_UNAVAILABLE
    )
    await set_setting(hass, entry, TARGET, 60)
    assert entry.runtime_data.values[TARGET] == 30
    assert cover.commands == []


@pytest.mark.parametrize(
    "failure, reason",
    [
        ("unavailable", "source_unavailable"),
        ("missing", "source_unavailable"),
        ("removed", "source_unavailable"),
        ("restored", "invalid_position"),
    ],
)
async def test_source_lost_during_target_save(
    hass, hass_storage, cover, add_shutter, failure, reason
):
    """Retain an accepted write when its source disappears during saving, without replay."""
    entry = await add_shutter(cover)
    controller = entry.runtime_data
    original_save = controller.store.async_save

    async def save_then_lose_source(data):
        """Persist the accepted target, then simulate a source loss before dispatch."""
        await original_save(data)
        if failure == "missing":
            hass.states.async_remove(cover.entity_id)
        elif failure == "removed":
            er.async_get(hass).async_remove(cover.entity_id)
        elif failure == "restored":
            hass.states.async_set(
                cover.entity_id,
                "open",
                {ATTR_RESTORED: True, ATTR_CURRENT_POSITION: 70},
            )
        else:
            cover.report(70, available=False)

    with patch.object(
        controller.store, "async_save", side_effect=save_then_lose_source
    ):
        with pytest.raises(ServiceValidationError) as error:
            await set_setting(hass, entry, TARGET, 60)
    assert error.value.translation_key == reason
    await hass.async_block_till_done()
    assert controller.values[TARGET] == 60
    assert hass_storage[storage_key(entry.entry_id)]["data"][TARGET] == 60
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    if failure != "removed":
        cover.report(5)
        await hass.async_block_till_done()
        assert hass.states.get(number_id).state == "60"
    assert cover.commands == []


async def test_lost_position_support(hass, cover, add_shutter):
    """Recheck position support at every target write and retain skipped targets."""
    entry = await add_shutter(cover)
    cover._attr_supported_features = 0
    cover.async_write_ha_state()
    with pytest.raises(ServiceValidationError) as error:
        await set_setting(hass, entry, TARGET, 60)
    assert error.value.translation_key == "position_unsupported"
    assert entry.runtime_data.values[TARGET] == 60
    assert cover.commands == []


async def test_failed_action_keeps_target_and_never_retries(hass, cover, add_shutter):
    """Propagate a cover failure with its cause while retaining the changed target."""
    entry = await add_shutter(cover)
    cover.fail = True
    with pytest.raises(HomeAssistantError) as error:
        await set_setting(hass, entry, TARGET, 60)
    assert error.value.translation_key == "command_failed"
    assert error.value.__cause__ is not None
    assert entry.runtime_data.values[TARGET] == 60
    assert (
        hass.states.get(setting_entity_id(hass, entry, "sensor", TARGET)).state == "60"
    )
    cover.fail = False
    cover.report(70, available=False)
    cover.report(70)
    await hass.async_block_till_done()
    await set_setting(hass, entry, TARGET, 60)
    assert cover.commands == [40]


async def test_multiple_shutters_are_independent(hass, cover, add_shutter):
    """Keep independent targets, buffers, sensors, and source action routing."""
    other_cover = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other_cover])
    first = await add_shutter(cover)
    second = await add_shutter(other_cover)
    await set_setting(hass, first, BUFFER, 100)
    await set_setting(hass, first, TARGET, 70)
    await set_setting(hass, second, TARGET, 50)
    assert first.runtime_data.values == {TARGET: 70, BUFFER: 100}
    assert second.runtime_data.values == {TARGET: 50, BUFFER: 0}
    assert cover.commands == []
    assert other_cover.commands == [50]


@pytest.mark.parametrize(
    "value, expected", [(0, 0), (100, 100), (30.4, 30), (30.5, 31), ("25", 25)]
)
def test_normalization(value, expected):
    """Normalize valid slider writes using whole percent and half-up rounding."""
    assert normalize_percentage(value) == expected
    assert valid_percentage(value) == float(value)
