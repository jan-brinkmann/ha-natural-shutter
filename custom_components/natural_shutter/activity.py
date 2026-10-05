"""Record decisions and external alignment; notify phones only for suppression."""

import asyncio
import logging

from homeassistant.components.logbook import async_log_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import CONF_NOTIFICATION_SERVICE, DOMAIN, MOBILE_APP_SERVICE_PREFIX, TARGET

_LOGGER = logging.getLogger(__name__)


@callback
def async_log_target_activity(
    hass: HomeAssistant,
    entry: ConfigEntry,
    title: str,
    message: str,
    context: Context | None,
) -> None:
    """Associate an Activity entry with the current target number and virtual device."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, f"{entry.entry_id}_number_{TARGET}"
    )
    async_log_entry(
        hass, title, message, domain=DOMAIN, entity_id=entity_id, context=context
    )


async def async_report_alignment(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    source: str,
    previous_target: int,
    target: int,
    position: float,
    context: Context | None,
) -> None:
    """Log a persisted target change caused by external movement without phone push."""
    timestamp = dt_util.now().isoformat(sep=" ", timespec="seconds")
    translations = await async_get_translations(
        hass, hass.config.language, "common", [DOMAIN]
    )
    prefix = f"component.{DOMAIN}.common."
    title = translations[f"{prefix}external_alignment_title"].format(name=entry.title)
    message = translations[f"{prefix}external_alignment_message"].format(
        timestamp=timestamp,
        source=source,
        previous_target=previous_target,
        target=target,
        actual=f"{100 - position:g}",
        position=f"{position:g}",
    )
    async_log_target_activity(hass, entry, title, message, context)


async def async_report_decision(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    source: str,
    previous_target: int,
    target: int,
    position: float,
    buffer: int,
    context: Context | None,
    command_sent: bool,
) -> None:
    """Log a decision snapshot; only suppressed decisions may notify a phone.

    Set command_sent only after a successful cover service call; source position
    and buffer describe the decision before dispatch, not later physical travel.
    Associate the Activity entry with this mapping's target number, following
    entity renames. Use HA's local time and preserve the originating context.
    Notification failures are logged and never change settings or trigger a
    cover command; notification dispatch is limited to ten seconds.
    """
    timestamp = dt_util.now().isoformat(sep=" ", timespec="seconds")
    translations = await async_get_translations(
        hass, hass.config.language, "common", [DOMAIN]
    )
    prefix = f"component.{DOMAIN}.common."
    ha_target = 100 - target
    distance = abs(position - ha_target)
    reason = (
        "command_sent"
        if command_sent
        else "already_at_target"
        if distance == 0
        else "below_buffer"
    )
    title_key = (
        "movement_command_title" if command_sent else "movement_suppressed_title"
    )
    title = translations[f"{prefix}{title_key}"].format(name=entry.title)
    message = translations[f"{prefix}movement_decision_message"].format(
        timestamp=timestamp,
        source=source,
        reason=translations[f"{prefix}{reason}"],
        previous_target=previous_target,
        target=target,
        actual=f"{100 - position:g}",
        position=f"{position:g}",
        ha_target=ha_target,
        distance=f"{distance:g}",
        buffer=buffer,
    )
    async_log_target_activity(hass, entry, title, message, context)
    if command_sent:
        return
    service = entry.options.get(CONF_NOTIFICATION_SERVICE)
    if not service:
        return
    if not service.startswith(
        MOBILE_APP_SERVICE_PREFIX
    ) or not hass.services.has_service("notify", service):
        _LOGGER.warning(
            "Cannot notify %s for %s: notification service is unavailable; "
            "the Activity entry was recorded",
            service,
            entry.title,
        )
        return
    try:
        async with asyncio.timeout(10):
            await hass.services.async_call(
                "notify",
                service,
                {"title": title, "message": message},
                blocking=True,
                context=context,
            )
    except (HomeAssistantError, TimeoutError) as err:
        _LOGGER.warning(
            "Notification for %s via notify.%s failed; "
            "the Activity entry was recorded: %s",
            entry.title,
            service,
            err,
        )
