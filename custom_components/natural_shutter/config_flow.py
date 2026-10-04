"""Provide manual cover selection and safe reconfiguration through HA's UI."""

from typing import Any

import voluptuous as vol
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_SUPPORTED_FEATURES,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import CONF_INITIAL_TARGET, CONF_SOURCE, CONF_SOURCE_REGISTRY_ID, DOMAIN
from .source import (
    current_position,
    normalize_percentage,
    resolve_source,
    source_identity,
    supports_position,
)


@callback
def source_details(hass: HomeAssistant, entity_id: str) -> tuple[dict[str, Any], str]:
    """Validate an existing position-capable cover or raise a flow error key."""
    state = hass.states.get(entity_id)
    registry_entry = er.async_get(hass).async_get(entity_id)
    if not entity_id.startswith(f"{COVER_DOMAIN}.") or (
        state is None and registry_entry is None
    ):
        raise ValueError("source_not_found")
    features = (
        state.attributes.get(ATTR_SUPPORTED_FEATURES)
        if state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        else registry_entry.supported_features
        if registry_entry is not None
        else 0
    )
    if not supports_position(features):
        raise ValueError("position_unsupported")
    position = current_position(state)
    data = {
        CONF_SOURCE: entity_id,
        CONF_SOURCE_REGISTRY_ID: registry_entry.id if registry_entry else None,
        CONF_INITIAL_TARGET: normalize_percentage(100 - position)
        if position is not None
        else 0,
    }
    name = (
        state.attributes.get(ATTR_FRIENDLY_NAME) if state is not None else None
    ) or (
        registry_entry.name or registry_entry.original_name if registry_entry else None
    )
    return data, name or entity_id


class NaturalShutterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one entry per manually selected cover, rejecting duplicate mappings."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show manual selection and initialize settings without moving the cover."""
        return await self._async_select_source(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace a source or rename the mapping, retaining its storage for reload."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="entry_not_found")
        return await self._async_select_source(user_input, entry)

    async def _async_select_source(
        self, user_input: dict[str, Any] | None, entry: ConfigEntry | None = None
    ) -> ConfigFlowResult:
        """Validate a selection, enforce identity uniqueness, and finish the flow."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data, suggested_name = source_details(
                    self.hass, user_input[CONF_SOURCE]
                )
            except ValueError as err:
                errors[CONF_SOURCE] = str(err)
            else:
                for existing in self._async_current_entries():
                    if entry is not None and existing.entry_id == entry.entry_id:
                        continue
                    if (
                        data[CONF_SOURCE_REGISTRY_ID] is not None
                        and data[CONF_SOURCE_REGISTRY_ID]
                        == existing.data.get(CONF_SOURCE_REGISTRY_ID)
                    ) or data[CONF_SOURCE] == resolve_source(self.hass, existing.data):
                        return self.async_abort(reason="already_configured")
                identity = source_identity(data)
                await self.async_set_unique_id(identity)
                name = user_input.get(CONF_NAME, "").strip() or suggested_name
                if entry is not None:
                    data[CONF_INITIAL_TARGET] = entry.data[CONF_INITIAL_TARGET]
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=identity,
                        title=name,
                        data=data,
                        reason="reconfigure_successful",
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data=data)

        step = "reconfigure" if entry is not None else "user"
        defaults = (
            {
                CONF_SOURCE: resolve_source(self.hass, entry.data)
                or entry.data[CONF_SOURCE],
                CONF_NAME: entry.title,
            }
            if entry is not None
            else {}
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE): EntitySelector(
                    EntitySelectorConfig(domain=COVER_DOMAIN)
                ),
                vol.Optional(CONF_NAME): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or defaults
            ),
            errors=errors,
        )
