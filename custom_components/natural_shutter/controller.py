"""Persist settings, align stopped positions, and dispatch explicit target writes."""

import asyncio
import logging
from collections.abc import Callable
from typing import NoReturn

from homeassistant.components.cover import (
    ATTR_POSITION,
    SERVICE_SET_COVER_POSITION,
)
from homeassistant.components.cover import (
    DOMAIN as COVER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_CLOSING,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Context, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .activity import async_report_alignment, async_report_decision
from .const import (
    BUFFER,
    CONF_INITIAL_TARGET,
    CONF_SOURCE,
    CONF_SOURCE_REGISTRY_ID,
    DOMAIN,
    STORAGE_VERSION,
    TARGET,
    storage_key,
)
from .device import ShutterDeviceLink
from .position import ShutterPositionTracker
from .source import (
    current_position,
    normalize_percentage,
    resolve_source,
    source_identity,
    supports_position,
)

_LOGGER = logging.getLogger(__name__)


class ShutterController:
    """Own one mapping's values and serialize persistence and service dispatch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Create an inactive controller without reading or commanding a cover."""
        self.hass = hass
        self.entry = entry
        self.device_link = ShutterDeviceLink(hass, entry)
        self.values = {TARGET: 0, BUFFER: 0}
        self.store: Store[dict[str, int]] = Store(
            hass, STORAGE_VERSION, storage_key(entry.entry_id), atomic_writes=True
        )
        self._lock = asyncio.Lock()
        self._active = False
        self._listeners: dict[str, list[Callable[[], None]]] = {
            TARGET: [],
            BUFFER: [],
        }
        self._unsubscribe_registry: CALLBACK_TYPE | None = None
        self._unsubscribe_source: CALLBACK_TYPE | None = None
        self._tracked_source: str | None = None
        self._last_source_available = False
        self.position_tracker = ShutterPositionTracker(self)

    @property
    def source_available(self) -> bool:
        """Require a valid live position and an enabled source registry entry."""
        source = resolve_source(self.hass, self.entry.data)
        if source is None or current_position(self.hass.states.get(source)) is None:
            return False
        registry_entry = er.async_get(self.hass).async_get(source)
        return registry_entry is None or not registry_entry.disabled

    async def async_load(self) -> None:
        """Restore the buffer and align an idle target with a valid live position.

        During motion or without a live position, retain the saved target or
        initial fallback. A moving source is aligned after the reported stop.
        Persist the resulting settings before activation without calling a setter
        or dispatching any command. Invalid saved data stops setup with an error.
        After validation, register the owned device and track source device links.
        """
        stored = await self.store.async_load()
        if stored is None:
            self.values = {
                TARGET: normalize_percentage(self.entry.data[CONF_INITIAL_TARGET]),
                BUFFER: 0,
            }
        else:
            try:
                self.values = {
                    TARGET: normalize_percentage(stored[TARGET]),
                    BUFFER: normalize_percentage(stored[BUFFER]),
                }
            except (KeyError, TypeError, ValueError) as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="invalid_storage"
                ) from err
        source = resolve_source(self.hass, self.entry.data)
        state = self.hass.states.get(source) if source is not None else None
        position = current_position(state)
        if position is not None and state.state not in (STATE_OPENING, STATE_CLOSING):
            self.values[TARGET] = normalize_percentage(100 - position)
            self.position_tracker.async_finished(self.position_tracker.revision)
        if stored is None or self.values != stored:
            await self.store.async_save(dict(self.values))
        self._active = True
        self.device_link.async_start()
        self._async_registry_changed(None)
        self._unsubscribe_registry = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_registry_changed
        )

    @callback
    def async_subscribe(self, key: str, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Subscribe to saved value or target availability changes; return cleanup."""
        self._listeners[key].append(listener)

        @callback
        def unsubscribe() -> None:
            """Remove the subscriber when its entity is unloaded."""
            self._listeners[key].remove(listener)

        return unsubscribe

    @callback
    def async_stop(self) -> None:
        """Block dispatch and detach source and device tracking without movement."""
        self._active = False
        self.position_tracker.async_cancel()
        self.device_link.async_stop()
        if self._unsubscribe_registry is not None:
            self._unsubscribe_registry()
            self._unsubscribe_registry = None
        if self._unsubscribe_source is not None:
            self._unsubscribe_source()
            self._unsubscribe_source = None
        self._tracked_source = None

    async def async_close(self) -> None:
        """Stop accepting writes and wait for an already running write to finish."""
        self.async_stop()
        async with self._lock:
            pass

    @callback
    def _async_registry_changed(self, event: Event | None) -> None:
        """Follow registry identities, device links, and availability without actions."""
        if not self._active:
            return
        source = resolve_source(self.hass, self.entry.data)
        registry_entry = er.async_get(self.hass).async_get(source) if source else None
        if registry_entry is not None and not self.entry.data.get(
            CONF_SOURCE_REGISTRY_ID
        ):
            data = {
                **self.entry.data,
                CONF_SOURCE: source,
                CONF_SOURCE_REGISTRY_ID: registry_entry.id,
            }
            self.hass.config_entries.async_update_entry(
                self.entry, data=data, unique_id=source_identity(data)
            )
        elif source is not None and source != self.entry.data[CONF_SOURCE]:
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, CONF_SOURCE: source}
            )
        elif (
            event is not None
            and event.data.get("action") == "remove"
            and event.data.get("entity_id") == self.entry.data[CONF_SOURCE]
        ):
            _LOGGER.warning(
                "Source %s was removed; settings are retained. Reconfigure or remove "
                "this Natural Shutter entry manually",
                self.entry.data[CONF_SOURCE],
            )
        self._async_track_source()
        self.device_link.async_refresh()

    @callback
    def _async_track_source(self) -> None:
        """Track the resolved source's state and detach any previous source listener."""
        source = resolve_source(self.hass, self.entry.data)
        if source != self._tracked_source:
            if self._unsubscribe_source is not None:
                self._unsubscribe_source()
            self.position_tracker.async_reset(
                self.hass.states.get(source) if source is not None else None,
                preserve_pending=self._tracked_source is not None,
            )
            self._tracked_source = source
            self._unsubscribe_source = (
                async_track_state_change_event(
                    self.hass, [source], self._async_source_changed
                )
                if source is not None
                else None
            )
        self._async_source_changed(None)

    @callback
    def _async_source_changed(self, event: Event | None) -> None:
        """Publish position availability and schedule passive alignment after motion."""
        if not self._active:
            return
        available = self.source_available
        if available != self._last_source_available:
            self._last_source_available = available
            for listener in tuple(self._listeners[TARGET]):
                listener()
        source = resolve_source(self.hass, self.entry.data)
        self.position_tracker.async_source_changed(
            self.hass.states.get(source) if source is not None else None,
            available,
            reported_moving=event is not None
            and any(
                state is not None and state.state in (STATE_OPENING, STATE_CLOSING)
                for state in (event.data.get("old_state"), event.data.get("new_state"))
            ),
        )

    async def async_align_target(self, revision: int, position: float) -> None:
        """Save a stopped position and log changed targets attributed to external motion.

        Serialize with explicit writes and revalidate feedback before and after
        persistence. Restore the previous storage snapshot if source changes or
        teardown invalidate a save in flight. Persistence failures keep the saved
        target and are logged; a later position change may attempt another alignment.
        Own movement feedback creates no additional Activity entry. Alignment never
        dispatches a command or phone notification.
        """
        async with self._lock:
            if not self._alignment_valid(revision, position):
                return
            target = normalize_percentage(100 - position)
            if target == self.values[TARGET]:
                self.position_tracker.async_finished(revision)
                return
            previous_target = self.values[TARGET]
            updated = {**self.values, TARGET: target}
            try:
                await self.store.async_save(updated)
                if not self._alignment_valid(revision, position):
                    await self.store.async_save(dict(self.values))
                    return
            except (OSError, HomeAssistantError):
                _LOGGER.exception(
                    "Cannot align target for %s; the previous target is retained",
                    self.entry.data[CONF_SOURCE],
                )
                return
            self.values = updated
            external = self.position_tracker.external_alignment
            context = self.position_tracker.alignment_context
            self.position_tracker.async_finished(revision)
            for listener in tuple(self._listeners[TARGET]):
                listener()
            if external:
                await async_report_alignment(
                    self.hass,
                    self.entry,
                    source=resolve_source(self.hass, self.entry.data),
                    previous_target=previous_target,
                    target=target,
                    position=position,
                    context=context,
                )

    def _alignment_valid(self, revision: int, position: float) -> bool:
        """Reject stale callbacks, invalid positions, and ongoing source movement."""
        source = resolve_source(self.hass, self.entry.data)
        state = self.hass.states.get(source) if source is not None else None
        return (
            self._active
            and revision == self.position_tracker.revision
            and self.source_available
            and state.state not in (STATE_OPENING, STATE_CLOSING)
            and current_position(state) == position
        )

    async def async_set_value(
        self, key: str, value: float, context: Context | None = None
    ) -> None:
        """Save a changed setting; only target writes may issue one cover command.

        Writes are processed in lock acquisition order, including the blocking
        action call, Activity reporting, and optional suppression notification.
        Errors never roll back a saved target or queue a retry.
        """
        try:
            normalized = normalize_percentage(value)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_percentage"
            ) from err

        async with self._lock:
            if not self._active:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="entry_unloaded"
                )
            if normalized == self.values[key]:
                return
            previous_target = self.values[TARGET]
            updated = {**self.values, key: normalized}
            await self.store.async_save(updated)
            self.values = updated
            if key == TARGET:
                self.position_tracker.async_target_changed()
            for listener in tuple(self._listeners[key]):
                listener()
            if key == TARGET and self._active:
                await self._async_command(normalized, previous_target, context)

    async def _async_command(
        self, target: int, previous_target: int, context: Context | None
    ) -> None:
        """Report suppressed writes or successful commands under the buffer rule."""
        source = resolve_source(self.hass, self.entry.data)
        if (
            source is None
            or (state := self.hass.states.get(source)) is None
            or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        ):
            self._raise_skipped("source_unavailable")
        position = current_position(state)
        if position is None:
            self._raise_skipped("invalid_position")
        registry_entry = er.async_get(self.hass).async_get(source)
        if (
            registry_entry is not None and registry_entry.disabled
        ) or not supports_position(state.attributes.get(ATTR_SUPPORTED_FEATURES)):
            self._raise_skipped("position_unsupported")

        ha_target = 100 - target
        distance = abs(position - ha_target)
        if distance == 0 or distance < self.values[BUFFER]:
            await async_report_decision(
                self.hass,
                self.entry,
                source=source,
                previous_target=previous_target,
                target=target,
                position=position,
                buffer=self.values[BUFFER],
                context=context,
                command_sent=False,
            )
            return
        command_context = context or Context()
        self.position_tracker.async_command_started(
            command_context, position, ha_target
        )
        try:
            await self.hass.services.async_call(
                COVER_DOMAIN,
                SERVICE_SET_COVER_POSITION,
                {ATTR_ENTITY_ID: source, ATTR_POSITION: ha_target},
                blocking=True,
                context=command_context,
            )
        except (HomeAssistantError, TimeoutError) as err:
            self.position_tracker.async_command_failed(command_context)
            _LOGGER.warning(
                "Position command for %s failed; target %s remains saved and will "
                "not be retried: %s",
                source,
                target,
                err,
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await async_report_decision(
            self.hass,
            self.entry,
            source=source,
            previous_target=previous_target,
            target=target,
            position=position,
            buffer=self.values[BUFFER],
            context=context,
            command_sent=True,
        )

    def _raise_skipped(self, reason: str) -> NoReturn:
        """Log and raise a translated action error after retaining the new target."""
        _LOGGER.warning(
            "Skipped position command for %s (%s); target %s remains saved. "
            "No command is queued",
            self.entry.data[CONF_SOURCE],
            reason,
            self.values[TARGET],
        )
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=reason)
