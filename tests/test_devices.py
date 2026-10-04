"""Verify integration visibility and reciprocal links without foreign mutations."""

from collections.abc import Callable
from copy import deepcopy
from itertools import count
from unittest.mock import patch

import pytest
from homeassistant.components import websocket_api
from homeassistant.components.config import config_entries as entry_api
from homeassistant.components.config import device_registry as device_api
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.natural_shutter.const import (
    BUFFER,
    CONF_INITIAL_TARGET,
    CONF_SOURCE,
    DOMAIN,
    MIN_HA_VERSION,
    TARGET,
    storage_key,
)

from .conftest import SimulatedCover, set_setting, setting_entity_id


@pytest.fixture
def actuator(hass: HomeAssistant) -> Callable[..., dr.DeviceEntry]:
    """Create source devices owned by independent simulated manufacturer entries."""
    serials = count(1)

    def create(name: str, keys: str = "both") -> dr.DeviceEntry:
        """Register a distinct actuator with identifiers, connections, or both."""
        entry = MockConfigEntry(domain="shelly", title=name, data={})
        entry.add_to_hass(hass)
        serial = next(serials)
        return dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={("shelly", name)} if keys != "connections" else set(),
            connections={(dr.CONNECTION_NETWORK_MAC, f"00:11:22:33:44:{serial:02x}")}
            if keys != "identifiers"
            else set(),
            name=name,
            manufacturer="Simulated actuator manufacturer",
            model="Position actuator",
            configuration_url="http://example.local/settings",
            hw_version="1",
            sw_version="2",
            serial_number=name,
        )

    return create


@pytest.fixture
async def registry_client(hass, hass_ws_client):
    """Connect to HA's real WebSocket APIs used by integration and device pages."""
    client = await hass_ws_client(hass)
    device_api.async_setup(hass)
    websocket_api.async_register_command(hass, entry_api.config_entries_get)
    return client


async def linked_devices(client, device_id: str) -> set[str]:
    """Query HA's device-page endpoint and return the reciprocal device IDs."""
    await client.send_json_auto_id(
        {
            "type": "config/device_registry/list_linked_devices",
            "device_id": device_id,
        }
    )
    response = await client.receive_json()
    assert response["success"], response
    return set(response["result"]["linked_devices"])


def own_device(hass, entry) -> dr.DeviceEntry:
    """Resolve the virtual device by its stable identity within its own entry."""
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    return device


async def test_all_mappings_appear_in_integrations(
    hass, cover, add_shutter, registry_client
):
    """Return every mapping in the integration-page filter rather than Helpers."""
    other = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([other])
    first = await add_shutter(cover)
    second = await add_shutter(other)
    await registry_client.send_json_auto_id(
        {"type": "config_entries/get", "domain": DOMAIN, "type_filter": ["device"]}
    )
    response = await registry_client.receive_json()
    assert response["success"], response
    assert {entry["entry_id"] for entry in response["result"]} == {
        first.entry_id,
        second.entry_id,
    }
    assert {entry["domain"] for entry in response["result"]} == {DOMAIN}
    for entry in (first, second):
        entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        assert len(entities) == 4
        assert {entity.device_id for entity in entities} == {own_device(hass, entry).id}
    await registry_client.send_json_auto_id(
        {"type": "config_entries/get", "domain": DOMAIN, "type_filter": ["helper"]}
    )
    assert (await registry_client.receive_json())["result"] == []
    assert cover.commands == other.commands == []


@pytest.mark.parametrize("keys", ["identifiers", "connections", "both"])
@pytest.mark.parametrize("available", [True, False])
async def test_reciprocal_links_preserve_actuator(
    hass, cover, add_shutter, actuator, registry_client, keys, available
):
    """Expose both navigation directions while preserving source ownership and data."""
    registry = dr.async_get(hass)
    source = actuator("Living room actuator", keys)
    er.async_get(hass).async_update_entity(cover.entity_id, device_id=source.id)
    cover.report(70, available=available)
    await hass.async_block_till_done()
    source_entity = er.async_get(hass).async_get(cover.entity_id)
    snapshot = deepcopy(source.dict_repr)
    changed_devices = []

    def record_update(event):
        """Record device changes to detect unexpected source-device writes."""
        changed_devices.append(event.data["device_id"])

    unsubscribe = hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, record_update)
    try:
        entry = await add_shutter(cover, "Living room shutter")
        own = own_device(hass, entry)
        assert own.id != source.id
        assert own.config_entry_id == entry.entry_id
        assert own.manufacturer == "Natural Shutter"
        assert own.name == "Living room shutter"
        assert own.identifiers == {(DOMAIN, entry.entry_id)} | source.identifiers
        assert own.connections == source.connections
        assert await linked_devices(registry_client, own.id) == {source.id}
        assert await linked_devices(registry_client, source.id) == {own.id}
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert own_device(hass, entry).id == own.id
        assert await linked_devices(registry_client, source.id) == {own.id}
        assert await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
        assert registry.async_get(own.id) is None
        assert await linked_devices(registry_client, source.id) == set()
    finally:
        unsubscribe()
    assert set(changed_devices) == {own.id}
    assert registry.async_get(source.id) is source
    assert registry.async_get(source.id).dict_repr == snapshot
    assert er.async_get(hass).async_get(cover.entity_id) is source_entity
    assert cover.commands == []


async def test_source_device_changes_refresh_links(
    hass, hass_storage, cover, add_shutter, actuator, registry_client
):
    """Follow device reassignment and changed keys without changing settings or IDs."""
    registry = dr.async_get(hass)
    first = actuator("First actuator")
    replacement = actuator("Replacement actuator")
    entities = er.async_get(hass)
    entities.async_update_entity(cover.entity_id, device_id=first.id)
    entry = await add_shutter(cover)
    own_id = own_device(hass, entry).id
    settings = deepcopy(hass_storage[storage_key(entry.entry_id)])
    entities.async_update_entity(cover.entity_id, device_id=replacement.id)
    await hass.async_block_till_done()
    assert own_device(hass, entry).id == own_id
    assert await linked_devices(registry_client, own_id) == {replacement.id}
    assert await linked_devices(registry_client, first.id) == set()
    assert registry.async_get(first.id) is first
    snapshot = deepcopy(replacement.dict_repr)
    assert registry.async_get(replacement.id).dict_repr == snapshot

    updated = registry.async_update_device(
        replacement.id,
        new_identifiers={("shelly", "Replacement serial")},
        new_connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
    )
    await hass.async_block_till_done()
    own = own_device(hass, entry)
    assert own.identifiers == {(DOMAIN, entry.entry_id)} | updated.identifiers
    assert own.connections == updated.connections
    assert await linked_devices(registry_client, updated.id) == {own_id}
    assert registry.async_get(updated.id) is updated
    assert hass_storage[storage_key(entry.entry_id)] == settings
    assert cover.commands == []


async def test_late_device_registration_and_source_removal(
    hass, cover, add_shutter, actuator, registry_client
):
    """Add a missing link later and drop it when the pinned source is removed."""
    entry = await add_shutter(cover)
    own_id = own_device(hass, entry).id
    assert await linked_devices(registry_client, own_id) == set()
    source = actuator("Late actuator")
    entities = er.async_get(hass)
    entities.async_update_entity(cover.entity_id, device_id=source.id)
    await hass.async_block_till_done()
    assert await linked_devices(registry_client, own_id) == {source.id}
    source_id = cover.entity_id
    entities.async_remove(source_id)
    await hass.async_block_till_done()
    assert own_device(hass, entry).identifiers == {(DOMAIN, entry.entry_id)}
    assert own_device(hass, entry).connections == set()
    assert await linked_devices(registry_client, source.id) == set()
    entities.async_get_or_create(
        "cover",
        "test",
        "unrelated",
        suggested_object_id=source_id.split(".")[1],
        device_id=source.id,
    )
    await hass.async_block_till_done()
    assert await linked_devices(registry_client, own_id) == set()
    assert dr.async_get(hass).async_get(source.id) is source
    assert cover.commands == []


async def test_reconfigure_replaces_only_owned_link(
    hass, cover, add_shutter, actuator, registry_client
):
    """Keep virtual device and entities stable while switching actuator navigation."""
    registry = dr.async_get(hass)
    first = actuator("First actuator")
    second = actuator("Second actuator")
    er.async_get(hass).async_update_entity(cover.entity_id, device_id=first.id)
    replacement = SimulatedCover("Bedroom", 10)
    await hass.data["cover"].async_add_entities([replacement])
    er.async_get(hass).async_update_entity(replacement.entity_id, device_id=second.id)
    entry = await add_shutter(cover)
    own_id = own_device(hass, entry).id
    number_id = setting_entity_id(hass, entry, "number", TARGET)
    await set_setting(hass, entry, BUFFER, 15)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        data={CONF_SOURCE: replacement.entity_id, CONF_NAME: "Bedroom shutter"},
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert own_device(hass, entry).id == own_id
    assert own_device(hass, entry).name == "Bedroom shutter"
    assert setting_entity_id(hass, entry, "number", TARGET) == number_id
    assert entry.runtime_data.values == {TARGET: 90, BUFFER: 15}
    assert await linked_devices(registry_client, own_id) == {second.id}
    assert await linked_devices(registry_client, first.id) == set()
    assert await linked_devices(registry_client, second.id) == {own_id}
    assert registry.async_get(first.id) is first
    assert registry.async_get(second.id) is second
    assert cover.commands == replacement.commands == []


async def test_child_source_links_parent_actuator(
    hass, cover, add_shutter, actuator, registry_client
):
    """Use the parent actuator when HA exposes a cover as a child channel device."""
    registry = dr.async_get(hass)
    parent = actuator("Multi-channel actuator")
    child = registry.async_get_or_create_child(
        config_entry_id=parent.config_entry_id,
        parent_device_id=parent.id,
        identifiers={("shelly", "channel_1")},
        name="Shutter channel",
    )
    er.async_get(hass).async_update_entity(cover.entity_id, device_id=child.id)
    entry = await add_shutter(cover)
    own = own_device(hass, entry)
    assert await linked_devices(registry_client, own.id) == {parent.id}
    assert await linked_devices(registry_client, parent.id) == {own.id}
    assert ("shelly", "channel_1") not in own.identifiers
    assert registry.async_get(parent.id) is parent
    assert registry.async_get(child.id) is child
    assert cover.commands == []


async def test_unload_detaches_device_tracking(hass, cover, add_shutter, actuator):
    """Ignore late registry callbacks after unloading without losing the stored link."""
    source = actuator("Living room actuator")
    er.async_get(hass).async_update_entity(cover.entity_id, device_id=source.id)
    entry = await add_shutter(cover)
    own = own_device(hass, entry)
    link = entry.runtime_data.device_link
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert link._unsubscribe is None
    dr.async_get(hass).async_update_device(
        source.id, new_identifiers={("shelly", "New serial")}, new_connections=set()
    )
    await hass.async_block_till_done()
    link.async_refresh()
    assert dr.async_get(hass).async_get(own.id) is own
    assert cover.commands == []


@pytest.mark.parametrize("version", ["2024.6.0", "2026.7.4", "2026.8.0b0"])
async def test_older_home_assistant_stops_before_device_or_storage_writes(
    hass, hass_storage, cover, actuator, version
):
    """Reject unsafe HA versions with a translated setup error and no source writes."""
    source = actuator("Living room actuator")
    er.async_get(hass).async_update_entity(cover.entity_id, device_id=source.id)
    await hass.async_block_till_done()
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_SOURCE: cover.entity_id, CONF_INITIAL_TARGET: 30}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.natural_shutter.HA_VERSION", version):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "unsupported_home_assistant"
    assert entry.error_reason_translation_placeholders == {"version": MIN_HA_VERSION}
    assert dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id) == []
    assert storage_key(entry.entry_id) not in hass_storage
    assert dr.async_get(hass).async_get(source.id) is source
    assert cover.commands == []
