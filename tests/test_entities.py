"""Check slider contracts and numeric history sensors with HA translations."""

import pytest
from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations

from custom_components.natural_shutter.const import BUFFER, DOMAIN, TARGET, storage_key

from .conftest import SimulatedCover, set_setting, setting_entity_id


async def test_slider_and_history_contract(hass, cover, add_shutter):
    """Expose percent sliders and sensors that track only saved settings."""
    entry = await add_shutter(cover)
    for key, expected in ((TARGET, "30"), (BUFFER, "0")):
        number = hass.states.get(setting_entity_id(hass, entry, "number", key))
        sensor = hass.states.get(setting_entity_id(hass, entry, "sensor", key))
        assert number.state == sensor.state == expected
        assert number.attributes["mode"] == "slider"
        assert number.attributes["min"] == 0
        assert number.attributes["max"] == 100
        assert number.attributes["step"] == 1
        assert (
            number.attributes["unit_of_measurement"]
            == sensor.attributes["unit_of_measurement"]
            == "%"
        )
        assert "state_class" not in sensor.attributes
        assert number.attributes["friendly_name"] != sensor.attributes["friendly_name"]
    await set_setting(hass, entry, BUFFER, 100)
    await set_setting(hass, entry, TARGET, 70)
    assert (
        hass.states.get(setting_entity_id(hass, entry, "sensor", TARGET)).state == "70"
    )
    assert (
        hass.states.get(setting_entity_id(hass, entry, "sensor", BUFFER)).state == "100"
    )
    cover.report(10, available=False)
    await hass.async_block_till_done()
    for kind in ("number", "sensor"):
        assert hass.states.get(setting_entity_id(hass, entry, kind, TARGET)).state == (
            STATE_UNAVAILABLE if kind == "number" else "70"
        )
        assert (
            hass.states.get(setting_entity_id(hass, entry, kind, BUFFER)).state == "100"
        )
    assert cover.commands == []


@pytest.mark.parametrize(
    "state, attributes",
    [
        (STATE_UNAVAILABLE, {"current_position": 70}),
        (STATE_UNKNOWN, {"current_position": 70}),
        (None, {}),
        ("open", {ATTR_RESTORED: True, "current_position": 70}),
    ],
)
async def test_target_availability_follows_source(
    hass, hass_storage, cover, add_shutter, state, attributes
):
    """Skip offline target actions and restore the saved value on reconnection."""
    entry = await add_shutter(cover)
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    snapshot = dict(hass_storage[storage_key(entry.entry_id)]["data"])
    if state is None:
        hass.states.async_remove(cover.entity_id)
    else:
        hass.states.async_set(cover.entity_id, state, attributes)
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    await set_setting(hass, entry, TARGET, 60)
    assert entry.runtime_data.values == snapshot
    assert hass_storage[storage_key(entry.entry_id)]["data"] == snapshot
    assert (
        hass.states.get(setting_entity_id(hass, entry, "sensor", TARGET)).state == "30"
    )
    await set_setting(hass, entry, BUFFER, 10)
    assert (
        hass.states.get(setting_entity_id(hass, entry, "number", BUFFER)).state == "10"
    )
    cover.report(5)
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == "30"
    assert entry.runtime_data.values == {TARGET: 30, BUFFER: 10}
    assert cover.commands == []


async def test_initial_offline_target_is_unavailable(hass, cover, add_shutter):
    """Create an unavailable target with its zero fallback until the source returns."""
    cover.report(70, available=False)
    entry = await add_shutter(cover)
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    assert (
        hass.states.get(setting_entity_id(hass, entry, "sensor", TARGET)).state == "0"
    )
    cover.report(70)
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == "0"
    assert cover.commands == []


async def test_disabled_source_target_is_unavailable(hass, cover, add_shutter):
    """Treat a disabled registry source as unavailable even if its state still exists."""
    entry = await add_shutter(cover)
    source_id = cover.entity_id
    er.async_get(hass).async_update_entity(
        source_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    assert hass.states.get(number_id).state == STATE_UNAVAILABLE
    er.async_get(hass).async_update_entity(source_id, disabled_by=None)
    hass.states.async_set(source_id, "open", {"current_position": 70})
    await hass.async_block_till_done()
    assert hass.states.get(number_id).state == "30"
    assert cover.commands == []


async def test_source_availability_is_independent(hass, cover, add_shutter):
    """Limit a source outage to its own target while other mappings remain usable."""
    other = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other])
    first = await add_shutter(cover)
    second = await add_shutter(other)
    cover.report(70, available=False)
    await hass.async_block_till_done()
    assert (
        hass.states.get(setting_entity_id(hass, first, "number", TARGET)).state
        == STATE_UNAVAILABLE
    )
    assert (
        hass.states.get(setting_entity_id(hass, second, "number", TARGET)).state == "90"
    )
    assert cover.commands == other.commands == []


async def test_device_grouping(hass, cover, add_shutter):
    """Group all four entities on an owned virtual device named for the source."""
    entry = await add_shutter(cover, "Kitchen shutter")
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    device_ids = {entity.device_id for entity in entities}
    assert len(device_ids) == 1
    device = dr.async_get(hass).async_get(device_ids.pop())
    assert device.name == "Kitchen shutter"
    assert device.identifiers == {(DOMAIN, entry.entry_id)}
    assert cover.commands == []


async def test_german_and_english_names(hass, cover, add_shutter):
    """Resolve both languages through HA's actual entity translation machinery."""
    await add_shutter(cover)
    for language, target, buffer in (
        ("de", "Ziel-Position", "Puffer"),
        ("en", "Target position", "Buffer"),
    ):
        translations = await async_get_translations(hass, language, "entity", {DOMAIN})
        assert (
            translations[f"component.{DOMAIN}.entity.number.target_position.name"]
            == target
        )
        assert translations[f"component.{DOMAIN}.entity.number.buffer.name"] == buffer
        assert (
            translations[f"component.{DOMAIN}.entity.sensor.target_position.name"]
            != target
        )
        assert translations[f"component.{DOMAIN}.entity.sensor.buffer.name"] != buffer
    assert cover.commands == []
