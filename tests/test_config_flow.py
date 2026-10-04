"""Verify manual selection, stable identities, and non-actuating reconfiguration."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.helpers import entity_registry as er

from custom_components.natural_shutter.config_flow import NaturalShutterConfigFlow
from custom_components.natural_shutter.const import (
    BUFFER,
    CONF_INITIAL_TARGET,
    CONF_SOURCE,
    CONF_SOURCE_REGISTRY_ID,
    DOMAIN,
    TARGET,
)

from .conftest import SimulatedCover, set_setting, setting_entity_id


async def test_manual_selection_and_duplicate(hass, cover, add_shutter):
    """Create exactly four entities manually and reject the same source twice."""
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert form["type"] == "form"
    assert not hass.config_entries.async_entries(DOMAIN)
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_SOURCE: cover.entity_id}
    )
    await hass.async_block_till_done()
    entry = result["result"]
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert sorted(entity.domain for entity in entities) == [
        "number",
        "number",
        "sensor",
        "sensor",
    ]
    assert (
        entry.data[CONF_SOURCE_REGISTRY_ID]
        == er.async_get(hass).async_get(cover.entity_id).id
    )
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_SOURCE: cover.entity_id}
    )
    assert duplicate["reason"] == "already_configured"
    assert cover.commands == []


@pytest.mark.parametrize("entity_id", ["cover.missing", "sensor.wrong_domain"])
async def test_invalid_source(hass, cover, entity_id):
    """Reject absent sources and entities from other domains without actions."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_SOURCE: entity_id}
    )
    assert result["errors"] == {CONF_SOURCE: "source_not_found"}
    assert cover.commands == []


async def test_unsupported_source(hass, cover):
    """Reject a cover that does not advertise absolute position commands."""
    cover._attr_supported_features = 0
    cover.async_write_ha_state()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_SOURCE: cover.entity_id}
    )
    assert result["errors"] == {CONF_SOURCE: "position_unsupported"}
    assert cover.commands == []


@pytest.mark.parametrize(
    "position, expected",
    [(70, 30), (25.5, 75), (None, 0), ("nan", 0), (-1, 0), (101, 0)],
)
async def test_initial_settings(hass, cover, add_shutter, position, expected):
    """Align at setup, fall back to zero, and ignore subsequent position reports."""
    cover.report(position)
    entry = await add_shutter(cover)
    assert entry.runtime_data.values == {TARGET: expected, BUFFER: 0}
    cover.report(10)
    await hass.async_block_till_done()
    assert entry.runtime_data.values == {TARGET: expected, BUFFER: 0}
    assert cover.commands == []


async def test_initial_unavailable(hass, cover, add_shutter):
    """Allow an offline registry-backed cover and keep the initialized zero target."""
    cover.report(70, available=False)
    entry = await add_shutter(cover)
    assert entry.runtime_data.values == {TARGET: 0, BUFFER: 0}
    cover.report(70)
    await hass.async_block_till_done()
    assert entry.runtime_data.values == {TARGET: 0, BUFFER: 0}
    assert cover.commands == []


async def test_reconfigure_aligns_target_and_preserves_buffer(hass, cover, add_shutter):
    """Align with the replacement source while retaining the buffer and entity IDs."""
    entry = await add_shutter(cover)
    await set_setting(hass, entry, BUFFER, 15)
    replacement = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([replacement])
    old_ids = {
        setting_entity_id(hass, entry, kind, key)
        for kind in ("number", "sensor")
        for key in (TARGET, BUFFER)
    }
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_SOURCE: replacement.entity_id, CONF_NAME: "New label"}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "New label"
    assert entry.data[CONF_SOURCE] == replacement.entity_id
    assert entry.runtime_data.values == {TARGET: 90, BUFFER: 15}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert old_ids == {
        setting_entity_id(hass, entry, kind, key)
        for kind in ("number", "sensor")
        for key in (TARGET, BUFFER)
    }
    assert cover.commands == replacement.commands == []


@pytest.mark.parametrize("position, expected", [(10, 90), (None, 30)])
async def test_delayed_setup_uses_live_position_or_fallback(
    hass, cover, position, expected
):
    """Prefer the live position at load, using the selection snapshot as a fallback."""
    with patch(
        "custom_components.natural_shutter.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_SOURCE: cover.entity_id}
        )
        await hass.async_block_till_done()
    entry = result["result"]
    assert entry.data[CONF_INITIAL_TARGET] == 30
    cover.report(position)
    from custom_components.natural_shutter.controller import ShutterController

    controller = ShutterController(hass, entry)
    await controller.async_load()
    assert controller.values[TARGET] == expected
    controller.async_stop()
    assert cover.commands == []


async def test_unregistered_source_and_identity_promotion(hass, cover, add_shutter):
    """Use an unregistered source and pin a stable identity once it becomes available."""
    source = SimulatedCover("Unregistered", 40)
    source._attr_unique_id = None
    await hass.data["cover"].async_add_entities([source])
    entry = await add_shutter(source)
    assert entry.data[CONF_SOURCE_REGISTRY_ID] is None
    assert entry.unique_id == f"entity:{source.entity_id}"
    assert entry.runtime_data.values == {TARGET: 60, BUFFER: 0}
    await set_setting(hass, entry, TARGET, 70)
    assert source.commands == [30]

    registry = er.async_get(hass)
    hass.states.async_remove(source.entity_id)
    registered = registry.async_get_or_create(
        "cover",
        "test",
        "promoted",
        suggested_object_id=source.entity_id.split(".", 1)[1],
    )
    assert registered.entity_id == source.entity_id
    source.report(40)
    await hass.async_block_till_done()
    assert entry.data[CONF_SOURCE_REGISTRY_ID] == registered.id
    assert entry.unique_id == f"registry:{registered.id}"
    registry.async_update_entity(
        source.entity_id, new_entity_id="cover.promoted_source"
    )
    await hass.async_block_till_done()
    assert entry.data[CONF_SOURCE] == "cover.promoted_source"
    assert entry.runtime_data.values == {TARGET: 70, BUFFER: 0}
    assert source.commands == [30]
    assert cover.commands == []


async def test_no_automatic_mapping_of_new_covers(hass, cover, add_shutter):
    """Ignore covers added after setup until the user explicitly selects them."""
    entry = await add_shutter(cover)
    new_cover = SimulatedCover("New cover", 20)
    await hass.data["cover"].async_add_entities([new_cover])
    await hass.async_block_till_done()
    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    assert (
        len(er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)) == 4
    )
    assert cover.commands == new_cover.commands == []


async def test_concurrent_duplicate_selection(hass, cover):
    """Concurrent manual selections of one cover cannot create duplicate mappings."""
    results = await asyncio.gather(
        *[
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_USER},
                data={CONF_SOURCE: cover.entity_id},
            )
            for _ in range(2)
        ]
    )
    await hass.async_block_till_done()
    assert sorted(result["type"] for result in results) == ["abort", "create_entry"]
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert cover.commands == []


async def test_reconfigure_cannot_duplicate_another_source(hass, cover, add_shutter):
    """Reject reconfiguration to a cover already owned by another mapping."""
    first = await add_shutter(cover)
    other = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other])
    await add_shutter(other)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": first.entry_id},
        data={CONF_SOURCE: other.entity_id},
    )
    assert result["reason"] == "already_configured"
    assert first.data[CONF_SOURCE] == cover.entity_id
    assert cover.commands == other.commands == []


async def test_reconfigure_after_entry_disappears(hass, cover):
    """Abort a stale reconfigure flow when its configuration entry was removed."""
    flow = NaturalShutterConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": "removed-entry"}
    result = await flow.async_step_reconfigure()
    assert result["reason"] == "entry_not_found"
    assert cover.commands == []
