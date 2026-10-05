"""Load the hardware-free manual demo and validate standard dashboard examples."""

from pathlib import Path

from homeassistant.config_entries import SOURCE_USER
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

from custom_components.natural_shutter.const import BUFFER, CONF_SOURCE, DOMAIN, TARGET

from .conftest import set_setting, setting_entity_id

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


async def test_simulated_cover_example(hass):
    """Exercise the shipped template-cover fixture with input-number actions only."""
    config = load_yaml(str(EXAMPLES / "simulated_cover.yaml"))
    assert await async_setup_component(hass, "input_number", config)
    assert await async_setup_component(hass, "template", config)
    await hass.async_block_till_done()
    source_id = "cover.natural_shutter_demo"
    helper_id = "input_number.natural_shutter_demo_position"
    assert hass.states.get(source_id).attributes["current_position"] == 70
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_SOURCE: source_id}
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = result["result"]
    calls = []

    def observe(event):
        """Trace cover service calls while the demo writes only a local helper."""
        if event.data["domain"] == "cover":
            calls.append(event.data["service"])

    remove = hass.bus.async_listen("call_service", observe)
    try:
        await set_setting(hass, entry, TARGET, 70)
        assert hass.states.get(helper_id).state == "30.0"
        await hass.services.async_call(
            "input_number",
            "set_value",
            {"entity_id": helper_id, "value": 15},
            blocking=True,
        )
        await hass.async_block_till_done()
        await set_setting(hass, entry, BUFFER, 10)
        assert (
            hass.states.get(setting_entity_id(hass, entry, "number", TARGET)).state
            == "70"
        )
        assert hass.states.get(helper_id).state == "15.0"
        assert calls == ["set_cover_position"]
    finally:
        remove()


def test_dashboard_example_uses_standard_cards():
    """Keep the dashboard example usable without custom cards or button actions."""
    card = load_yaml(str(EXAMPLES / "dashboard.yaml"))
    assert card["type"] == "vertical-stack"
    assert [child["type"] for child in card["cards"]] == [
        "entities",
        "history-graph",
        "logbook",
    ]
    assert len(card["cards"][0]["entities"]) == len(card["cards"][1]["entities"]) == 2
    assert card["cards"][2]["entities"] == ["number.living_room_target_position"]
