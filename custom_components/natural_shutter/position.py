"""Coalesce position feedback and attribute movement before passive alignment."""

from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import TYPE_CHECKING

from homeassistant.const import STATE_CLOSING, STATE_OPENING
from homeassistant.core import CALLBACK_TYPE, Context, State, callback
from homeassistant.helpers.event import async_call_later

from .const import (
    COMMAND_TRACK_SECONDS,
    CONF_POSITION_QUIET_SECONDS,
    DATA_POSITION_COMMANDS,
    DEFAULT_POSITION_QUIET_SECONDS,
    POSITION_SETTLE_SECONDS,
)
from .source import current_position, resolve_source, source_identity

if TYPE_CHECKING:
    from .controller import ShutterController


@dataclass(frozen=True)
class PositionCommand:
    """Remember one dispatched movement in memory, including across entry reloads."""

    source: str
    context: Context
    position: float
    target: int
    expires: float


class ShutterPositionTracker:
    """Track movement origin and invalidate stale alignment callbacks per source."""

    def __init__(self, controller: ShutterController) -> None:
        """Initialize tracking without observing or scheduling any source action."""
        self.controller = controller
        self.revision = 0
        self._last_position: float | None = None
        self._moving = False
        self._seen_moving = False
        self._needs_alignment = False
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._commands: dict[str, PositionCommand] = controller.hass.data.setdefault(
            DATA_POSITION_COMMANDS, {}
        )
        self.alignment_context: Context | None = None
        self.external_alignment = True

    @callback
    def async_command_started(
        self, context: Context, position: float, target: int
    ) -> None:
        """Mark dispatch before feedback arrives, bounding attribution to five minutes."""
        self._commands[self.controller.entry.entry_id] = PositionCommand(
            source_identity(self.controller.entry.data),
            context,
            position,
            target,
            monotonic() + COMMAND_TRACK_SECONDS,
        )
        self.external_alignment = False

    @callback
    def async_command_failed(self, context: Context) -> None:
        """Discard a failed dispatch without claiming later movement as our own."""
        command = self._commands.get(self.controller.entry.entry_id)
        if command is not None and command.context is context:
            self._commands.pop(self.controller.entry.entry_id)
            self.external_alignment = True

    def _own_command(self) -> PositionCommand | None:
        """Return only an unexpired command for this mapping's current source identity."""
        command = self._commands.get(self.controller.entry.entry_id)
        if command is not None and (
            command.source != source_identity(self.controller.entry.data)
            or monotonic() >= command.expires
        ):
            self._commands.pop(self.controller.entry.entry_id)
            return None
        return command

    @callback
    def _async_attribute_position(self, state: State, position: float) -> None:
        """Use action context and bounded travel to identify external position changes.

        Context-free hardware reports belong to a pending own command while they
        stay within its travel range and direction. A different user/parent
        context, reversed motion, or movement outside that range overrides it.
        Such reports cannot identify an unreported manual interruption along the
        same path; source integrations must supply origin information for certainty.
        """
        command = self._own_command()
        if command is not None:
            context_matches = (
                state.context.id == command.context.id
                or state.context.parent_id == command.context.id
            )
            opposite_motion = (
                state.state == STATE_OPENING and command.target < command.position
            ) or (state.state == STATE_CLOSING and command.target > command.position)
            outside_travel = not (
                min(command.position, command.target) - 1
                <= position
                <= max(command.position, command.target) + 1
            )
            if (
                (
                    not context_matches
                    and (
                        state.context.user_id is not None
                        or state.context.parent_id is not None
                    )
                )
                or opposite_motion
                or outside_travel
            ):
                self._commands.pop(self.controller.entry.entry_id)
                command = None
        self.external_alignment = command is None
        self.alignment_context = state.context

    @callback
    def async_cancel(self) -> None:
        """Invalidate queued work and remove the pending timer without movement."""
        self.revision += 1
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    @callback
    def async_reset(self, state: State | None, preserve_pending: bool = False) -> None:
        """Bind a baseline, preserving unfinished feedback across entity-ID renames."""
        previous_position = self._last_position
        pending = self._needs_alignment
        seen_moving = self._seen_moving
        previous_context = self.alignment_context
        previous_external = self.external_alignment
        self.async_cancel()
        self._last_position = current_position(state)
        self._moving = state is not None and state.state in (
            STATE_OPENING,
            STATE_CLOSING,
        )
        self._seen_moving = self._moving
        self._needs_alignment = self._moving
        self.alignment_context = None
        self.external_alignment = self._own_command() is None
        if preserve_pending:
            self._needs_alignment |= pending or (
                self._last_position is not None
                and self._last_position != previous_position
            )
            self._seen_moving |= seen_moving
            if self._last_position is None:
                self._last_position = previous_position
                self.alignment_context = previous_context
                self.external_alignment = previous_external
            else:
                self._async_attribute_position(state, self._last_position)

    @callback
    def async_target_changed(self) -> None:
        """Discard older feedback after a saved explicit target change."""
        source = resolve_source(self.controller.hass, self.controller.entry.data)
        state = self.controller.hass.states.get(source) if source is not None else None
        self.async_reset(state)
        self._needs_alignment = False

    @callback
    def async_source_changed(
        self, state: State | None, available: bool, reported_moving: bool = False
    ) -> None:
        """Wait for stopped motion or a quiet position interval before alignment.

        Invalid source data cancels timers while retaining any unfinished motion.
        Unrelated attributes and unchanged positions cannot restart an idle timer
        or replace a buffered target. Reported motion always prevents alignment.
        Preserve movement evidence from queued events even if the live state has
        already advanced to stopped before the event listener runs.
        """
        self._seen_moving |= reported_moving
        if (
            not available
            or state is None
            or (position := current_position(state)) is None
        ):
            self.async_cancel()
            return
        moving = state.state in (STATE_OPENING, STATE_CLOSING)
        changed = position != self._last_position
        stopped = self._moving and not moving
        if changed or stopped or moving:
            self._async_attribute_position(state, position)
        self._last_position = position
        self._moving = moving
        if changed:
            self._needs_alignment = True
        if moving:
            self._seen_moving = True
            self.async_cancel()
            return
        if not self._needs_alignment and not (
            stopped and self._own_command() is not None
        ):
            return
        if not changed and not stopped and self._cancel_timer is not None:
            return
        self.async_cancel()
        revision = self.revision
        delay = (
            POSITION_SETTLE_SECONDS
            if self._seen_moving
            else self.controller.entry.options.get(
                CONF_POSITION_QUIET_SECONDS, DEFAULT_POSITION_QUIET_SECONDS
            )
        )

        async def align(now: datetime) -> None:
            """Align the captured final position only if no newer event superseded it."""
            if revision != self.revision:
                return
            self._cancel_timer = None
            if not self._needs_alignment:
                self.async_finished(revision)
                return
            await self.controller.async_align_target(revision, position)

        self._cancel_timer = async_call_later(self.controller.hass, delay, align)

    @callback
    def async_finished(self, revision: int) -> None:
        """Clear the completed movement only for the current feedback generation."""
        if revision == self.revision:
            self._needs_alignment = False
            self._seen_moving = False
            self._commands.pop(self.controller.entry.entry_id, None)
            self.alignment_context = None
            self.external_alignment = True
