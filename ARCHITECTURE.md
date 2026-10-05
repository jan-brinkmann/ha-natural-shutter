# Natural Shutter architecture

## Components and data model

Natural Shutter is a config-entry-based device integration with the domain
`natural_shutter`. One manually selected cover corresponds to one config entry,
one owned virtual device, two number entities, and two sensor entities. There is
no discovery, YAML configuration for mappings, proxy cover, custom service, custom
card, or historical database. The integration has no third-party runtime packages.

| Component | Responsibility |
| --- | --- |
| `const.py` | Shared product name, domain, keys, platforms, storage key |
| `config_flow.py` | Manual source validation, duplicate checks, initial snapshot, reconfiguration, notification and quiet-interval options |
| `source.py` | Registry identity resolution and finite percentage validation |
| `controller.py` | Persistent settings, passive alignment, source availability, serialized explicit commands |
| `position.py` | Per-source movement tracking, quiet intervals, and cancellation of stale alignment callbacks |
| `activity.py` | Localized command, suppression, and external-alignment Activity, with optional suppression notifications |
| `device.py` | Reciprocal actuator links maintained only on the owned virtual device |
| `entity.py` | Stable entity IDs, virtual device grouping, subscription cleanup |
| `number.py` | Target and buffer sliders; explicit `async_set_native_value` |
| `sensor.py` | Numeric saved-setting history sensors |
| `__init__.py` | Setup, unload, and mapping-storage removal |

Config-entry data contains `source_entity_id`, optional `source_registry_id`, and
`initial_target`. The entry title is the user-selected label or source friendly
name. A `ShutterController` is assigned to typed `ConfigEntry.runtime_data`.
The current settings are an integer dictionary: `target_position` and `buffer`.
Config-entry options hold `position_quiet_seconds` (1–300, default 10) for sources
without movement status and `notification_service`: a registered `mobile_app_*`
service in the `notify` domain, or an empty string for disabled push. Existing
entries without this option default to disabled push. An Options Flow lists only
Companion App services and allows opt-out even when a saved service has disappeared.
The controller reads options directly; changing the recipient does not reload,
align the target, or issue a cover command. Source reconfiguration retains options.
Config-entry schema version and storage schema version are independent of the
integration's initial release version, which is defined in `manifest.json`.

## Source mapping and identities

At selection, the source must exist and advertise `CoverEntityFeature.SET_POSITION`.
An unavailable registry-backed source can use its registry feature mask; otherwise
the active state must advertise the feature. Active sources without a valid actual
position can still be selected, since their initial target is zero.

Config-entry unique IDs are `registry:<registry-entry-id>` when available, otherwise
`entity:<entity-id>`. Both registry identity and resolved source entity ID are checked
for duplicates; HA's in-progress flow protection also prevents parallel selection
of the same identity. If an already mapped unregistered source gains a registry
record, that identity is pinned without changing settings or dispatching commands.
Sources are never added automatically.

Loading and every explicit target write resolve the registry ID again. Renaming a
registered source therefore preserves routing and generated entity identities,
including when the mapping was unloaded during the rename. A rename preserves
pending position alignment; loading aligns an idle target with the live position.
A registry listener updates the cached source entity ID, logs removal, and rebinds
the source state subscription after a rename. Source state events publish target
availability transitions and schedule passive target alignment after movement.
They never dispatch an action.

If a pinned registry record disappears, resolution returns no source. It never
falls back to an entity ID that another device could reuse. The user can explicitly
rebind the mapping through **Reconfigure**, preserving the buffer and generated
entity identities. Its reload aligns the target with the replacement's live position
if valid and idle, retaining the saved target otherwise. A source without a registry
identity can only be tracked by its entity ID; after a rename it needs manual
reconfiguration. Such an ID can be reused
by HA, which is an unavoidable identity limitation for unregistered sources.

Generated unique IDs combine the mapping's immutable `entry_id`, platform kind,
and setting key. A separate virtual device groups all four entities under the
chosen shutter label. This avoids writing metadata into the manufacturer's device
or claiming ownership of its entities. `has_entity_name` and translation keys give
distinct names to sliders and sensors. Reconfiguring the label updates device naming
without changing unique IDs. Removal through HA's entry UI deletes one mapping.

The manifest classifies the integration as `device`, so HA's Integrations tab
groups all config entries under Natural Shutter instead of filtering them into
Helpers. Each config entry still owns exactly one virtual device.

The virtual device always retains `(natural_shutter, entry_id)` as its stable
identifier. `ShutterDeviceLink` reads the source entity's device and copies that
device's identifiers and connections onto the virtual device. Since HA 2026.8,
these keys are unique per config entry, allowing HA's `list_linked_devices` WebSocket
endpoint to discover both navigation directions without merging devices or changing
the source device. The implementation never adds our config entry to the source
device, moves source entities, or writes any manufacturer metadata. All device
lookups and updates for the virtual device are scoped to its own config entry.

Source entity reassignment, changed source device keys, and reconfiguration replace
old link keys on the same virtual device. Missing source registry records or devices
remove the link; temporary source unavailability keeps it. Unregistered sources have
no device to link. A child device resolves to its parent actuator because HA's
Linked devices API only matches main devices. The device registry subscription is
removed on unload and failed setup, and late callbacks cannot update devices.
Link maintenance has no path to persistence or movement commands.

## Persistence, initialization, and restoration

Each mapping uses HA's atomic `Store` with key `natural_shutter.<entry_id>` under
the configuration directory's `.storage`. This is a current-settings file, not a
history archive. It is independent of Recorder and stays outside integration files
during code updates. Saved data is validated before entities become active.
Damaged settings stop setup with a translated error, rather than becoming a target
of zero silently.

The config flow snapshots an initial fallback target: the rounded value of
`100 - current_position`, or zero if no valid live position exists. Buffer starts
at zero. A missing settings file initializes from this snapshot.

On every entry load, including startup, reload, and reconfiguration, the controller
reads the resolved source's current position. A valid idle value replaces the target
with the rounded value of `100 - current_position`; the buffer is retained. If the
source is missing, unknown, unavailable, restored, or has an invalid position, the
saved target or initial fallback remains. Resulting settings are saved before
activation when new or changed. This initialization calls neither the target setter
nor command dispatch, so the buffer cannot trigger or prevent it. If the source
reports opening or closing, the saved target remains until movement stops. Later
position reports can align the target as described below; the buffer is never
changed by source feedback.

Writes await `Store.async_save` before updating in-memory values, notifying entities,
or evaluating a target command. Loading calls no setter. Reload recreates the
controller, restores the settings file, and performs the non-actuating target
alignment above. Entry removal deletes only that file;
unloading retains it. HA manages disk error logging inside `Store`; durability still
depends on a functioning storage device and HA's storage lifecycle. No filesystem
transaction can also guarantee execution on an external physical device.

## Passive position alignment

`ShutterPositionTracker` observes the resolved source's live position and motion
state independently for each entry. A changed actual position marks alignment as
pending. While the source reports `opening` or `closing`, no timer may align the
target. At stop, a two-second grace period accepts late final positions; a changed
position restarts that period. A load during reported movement also schedules
alignment after stop, retaining the saved target throughout the movement.

Sources without motion states use a quiet interval, default ten seconds and
configurable per entry from 1 to 300 seconds. It restarts only for a changed
position, not unrelated attributes or repeated positions. This heuristic requires
an interval longer than the source's reporting gaps; position reports alone cannot
prove that movement has stopped. Source integrations own the correctness of both
positions and motion states.

Timers use HA's `async_call_later` and the event loop's monotonic clock. Each new
position, movement, unavailable source, explicit changed target, or teardown
invalidates older callbacks with a revision counter. Queued state events contribute
motion evidence, while their position is read from the latest live state to avoid
overwriting a newer explicit input with an old event. Source entity-ID rebinding
preserves pending movement evidence. Missing or invalid positions cancel timers
but retain unfinished movement for recovery.

Alignment acquires the same lock as explicit writes, checks the revision, live
position, availability, and idle state, then saves the rounded equivalent target.
The checks run again after persistence; invalidated writes restore the previous
storage snapshot rather than publishing a stale value. Save failures log an error
and retain the previous in-memory target; later changed feedback may try again.
Successful changes notify the target number and history sensor. External movement
also produces one localized target-alignment Activity entry, after persistence and
publication. Own movement feedback and unchanged rounded targets produce no such
entry. Alignment does not call the target setter, evaluate the buffer, dispatch
commands, report movement decisions, or send phone notifications. An unchanged
actual position cannot erase a target suppressed by the buffer.

Before dispatching a cover command, the tracker stores a `PositionCommand` with
source identity, action context, start position, requested HA position, and a
five-minute monotonic deadline. Suppressed writes create no command marker; failed
dispatch clears it. Source feedback carrying the same context or its direct child
belongs to the command. A different user/parent context, opposite movement state,
or position outside the commanded travel range (with one percentage point of
tolerance) clears the marker and identifies external movement. Reports without
origin metadata are attributed to an unexpired command within its range and
direction. The external Activity event preserves the context of the final report.

Command markers are scoped to entry IDs in transient `hass.data`, allowing a reload
during movement to preserve attribution. An idle load, completed alignment, or
reported stop without position changes through its grace period clears the marker.
A source identity change
or expired marker cannot suppress later external entries. Entry removal deletes
its marker; HA restart clears the in-memory cache. This provides bounded attribution,
not proof of causality: a same-path manual intervention without distinct origin
metadata during an own movement remains indistinguishable. No physical movement
is inferred from a successful action alone.

## Allowed trigger and excluded events

The only command entry point is the target number's `async_set_native_value`, invoked
by explicit UI or action writes such as `number.set_value`. The controller validates
and normalizes the input, then compares it to the saved value under its write lock.
Equal normalized values return without a save, notification, or command.

The buffer setter only saves and publishes its setting. Sensors only read stored
values. Setup, reconfiguration, unload, restart, restoration, registry events,
availability changes, actual position reports, external movements, and sensor
updates have no path to command dispatch. Passive alignment timers save settings
and log external target changes. There is no command retry queue or pending target replay. Scenes that
explicitly write the target are subject to the same equality check and validation
as any other explicit action.

## Conversion and buffer algorithm

Input values must be finite and within 0–100 before normalization; booleans, NaN,
infinity, and out-of-range values are rejected. Sliders use step 1. Explicit decimal
inputs are rounded to the nearest integer, with halves rounded up. Actual source
positions are validated but retain fractional precision.

For a changed normalized target `x`, HA target `t = 100 - x`, valid live source
position `a`, and saved buffer `b`, compute `d = abs(a - t)`.
Send one `cover.set_cover_position` action with `position: t` iff
`d > 0 and d >= b`. Buffer is a distance in percentage points and never offsets the
destination. Both directions, equality at the threshold, and endpoints follow this
same rule. The target is saved even when the buffer suppresses movement.

## Activity and suppression notifications

Only an accepted changed normalized target with valid source data reaches reporting.
The existing `d == 0 or d < b` branch produces one localized Activity entry, with
distinct reasons for an already reached target and a difference below the buffer.
An equality at the nonzero buffer threshold dispatches the existing cover command
and records a command entry after the blocking action returns successfully. Every
successful position command produces exactly one such entry, with no phone
notification. The source position is the snapshot used before dispatch; the
entry's timestamp is recorded after the successful action return. The entry
confirms service-call success, without asserting physical movement or target arrival.
Equal normalized writes, buffer changes, setup,
reload, source feedback, source validation errors, and cover-action failures do not
produce these diagnostics. Later feedback can align the saved target without
creating a decision entry or confirming physical arrival. Reporting adds no
command, target adjustment, or retry.

An external passive alignment that changes the saved target emits a **Target
updated** entry. It contains the previous/new target, final actual position on both
scales, source, and local timestamp, and explains that Natural Shutter sent no
command for this change. It uses the same target-number association for entity and
virtual-device Activity filters. There is no phone-notification path in this reporter.
Load-time alignment, unavailable or invalid positions, failed or invalidated saves,
and unchanged rounded targets emit no alignment entry.

The snapshot includes the entry name, resolved source entity ID, previous and new
saved target, actual position in Natural Shutter and HA scales, HA target, distance,
buffer, and reporting timestamp. `dt_util.now()` supplies HA's local time; the ISO
timestamp includes seconds and UTC offset. Messages use the standard translation
helper's `common` category in HA's configured language, with English fallback.

The standard `logbook.async_log_entry` helper emits an event with domain
`natural_shutter`, the originating action context, and the target number's current
registry entity ID. This association makes it visible in entity and virtual-device
Activity filters, including after renaming the target number. Activity/Logbook and
Recorder control visibility, filtering, and retention; no custom history is stored.
The manifest orders setup after Logbook and Notify when these optional integrations
are configured, without requiring them for slider operation.

For suppressed decisions, Activity is recorded before sending an optional `notify.mobile_app_*` message with
the same title, body, and context. The service is rechecked at dispatch. A missing
service, notification error, or notification timeout is logged without raising a
new target-write error or losing the Activity event. Blocking notification dispatch
is limited to ten seconds and remains inside the write lock, preserving decision
order and the saved buffer snapshot. Future writes use any changed phone option;
messages are neither queued nor retried.

## Availability and error handling

The target number's `available` property follows the resolved source's live state
and registry status. A missing, unknown, unavailable, restored, or disabled source,
or one without a finite position from 0 to 100, makes the target unavailable.
HA skips actions targeting this unavailable number,
leaving its saved value unchanged. The buffer and both history sensors remain
available. Reconnection republishes the saved target without movement; changed,
newly known, or unfinished positions can then align after the waiting period.
Lost position support on an otherwise live source is handled when an explicit
target write is dispatched.

An accepted changed target is saved first. If the source disappears during saving,
has an invalid actual position, becomes disabled, or loses position support, the
command path reports a warning and translated action error. The saved setting
remains in sensor history, even if the target slider is now unavailable. No action
is queued. Setting the same target again after reconnection is still a no-op;
another explicit target change is required for another attempt.

Source action failures propagate as translated `HomeAssistantError`, preserving the
original cause. Timeouts receive the same treatment. Neither case rolls back the
target or triggers a retry. The user's action context is passed to the delegated
cover action. The manufacturer integration owns communication, calibration, travel
direction, action latency, and feedback correctness. A source could go offline
between validation and dispatch; its integration determines the resulting error.

## Concurrency and teardown

One `asyncio.Lock` per mapping covers passive alignment, comparison, saving,
publishing, source validation, the blocking cover action, and decision reporting.
Requests are processed in lock acquisition order. An older command cannot overtake
a newer one. Buffer changes join the same
sequence, giving each target decision a consistent saved buffer. Different mappings
operate independently. Ordered writes are not debounced: each distinct explicit
target may dispatch its own command. A slow source action delays later writes for
that mapping. A suppressed write may also wait up to ten seconds for the selected
notification service before subsequent writes proceed.

Unload removes entity subscriptions, marks the controller inactive, detaches entity
registry, device registry, and source state tracking, and waits for an already running write. Late registry or
state callbacks cannot reattach tracking or publish updates. Unload cancels alignment
timers and invalidates in-flight passive saves. A save completing after the inactive
flag is set cannot dispatch a command. Already dispatched actions and physical travel
cannot be withdrawn. Waiting writes fail on the unloaded controller. Setup failure
also detaches all listeners. Subscription counts and teardown are tested explicitly.

## History sensors and Recorder

Sensors report the saved integer percentages, including suppressed or failed targets.
Each changed setting immediately notifies its corresponding slider and sensor.
Setting the same normalized value sends no notification. The target sensor reflects
the value aligned at load and after subsequent stopped movement. While the target
number is unavailable, its history sensor keeps the last stored numeric value.
Sensors carry `%` and suggested display precision zero.
They intentionally have no statistics state class: charting settings through ordinary
Recorder history preserves transitions without presenting hourly averages as an
archive of commands. Recorder filters and retention control history availability.
No history backdating or retention guarantees are implemented.

## Compatibility and official references

Both READMEs display the supplied `docs/banner.png` directly below their title.
The supplied square integration icon lives at
`custom_components/natural_shutter/brand/icon.png`. HA 2026.3+ discovers this local
brand directory automatically; no manifest icon field or custom HTTP view is needed.
The same file supplies logo, dark-mode, and high-resolution fallbacks through HA's
brands API. All supported HA versions include local brand discovery.

The declared minimum is HA **2026.8.0**, which introduced device ownership and
identifier uniqueness per config entry. The scoped lookup and reciprocal-link
APIs were checked in the official 2026.8.0 source. Setup compares HA's version
against the shared `MIN_HA_VERSION` before loading settings or registering devices;
older versions produce a translated `ConfigEntryError`. This also protects manual
installations that bypass HACS's minimum-version check. The pinned test stack uses
Python 3.14 and HA 2026.9.4; the minimum runtime has not been exercised in full.

References checked during implementation on 2026-10-04:

- [HA config flows](https://developers.home-assistant.io/docs/core/integration/config_flow/)
  and [runtime data](https://developers.home-assistant.io/blog/2024/04/30/store-runtime-data-inside-config-entry/).
- [Number entities](https://developers.home-assistant.io/docs/core/entity/number/),
  [sensor entities](https://developers.home-assistant.io/docs/core/entity/sensor/),
  and [localization](https://developers.home-assistant.io/docs/internationalization/core/).
- [Entity availability](https://developers.home-assistant.io/docs/core/entity/) and
  [state event subscriptions](https://developers.home-assistant.io/docs/integration_listen_events/)
  were checked when implementing source availability propagation.
- [HA integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/).
- [HA 2026.8 device ownership](https://developers.home-assistant.io/blog/2026/07/21/device-registry-single-config-entry/),
  its [device registry](https://github.com/home-assistant/core/blob/2026.8.0/homeassistant/helpers/device_registry.py),
  and [Linked devices endpoint](https://github.com/home-assistant/core/blob/2026.8.0/homeassistant/components/config/device_registry.py).
- [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/),
  [repository metadata](https://www.hacs.xyz/docs/publish/start/),
  [custom repository installation](https://www.hacs.xyz/docs/faq/custom_repositories/), and
  [HA brand images](https://developers.home-assistant.io/docs/core/integration/brand_images/).
- README organization was informed by the reachable
  [Manual Energy Metering](https://github.com/jan-brinkmann/ha-manual-energy-metering)
  and [Shelly LED Control](https://github.com/jan-brinkmann/ha-shelly-led-control)
  projects. At the owner's subsequent request, the same MIT licensing and codeowner
  were adopted. The owner has since created
  [jan-brinkmann/ha-natural-shutter](https://github.com/jan-brinkmann/ha-natural-shutter),
  which is available for installation through HACS as a custom repository.

References checked for suppression reporting on 2026-10-05:

- [Log activity](https://www.home-assistant.io/actions/logbook.log/) and
  [Activity card](https://www.home-assistant.io/dashboards/logbook/).
- [Companion App notifications](https://companion.home-assistant.io/docs/notifications/notifications-basic/)
  and [backend localization](https://developers.home-assistant.io/docs/internationalization/core/).
- The installed HA 2026.9.4 source for `logbook.async_log_entry`, Activity entity/device
  queries, translation fallback, `SelectSelector`, and `OptionsFlow` was inspected.
- HA's [device page](https://github.com/home-assistant/frontend/blob/dev/src/panels/config/devices/ha-config-device-page.ts)
  passes the device's entity IDs together with its device ID to the Activity card;
  the Recorder test uses that same combination and HA's entity filtering.

References checked for passive alignment on 2026-10-05:

- [Cover states and current position](https://developers.home-assistant.io/docs/core/entity/cover/)
  and [state event and timer helpers](https://developers.home-assistant.io/docs/integration_listen_events/).
- The installed HA 2026.9.4 timer implementation was inspected to confirm monotonic
  scheduling and cancellation behavior.
- [HA context](https://data.home-assistant.io/docs/context/) and the installed
  entity/service implementation were checked for action attribution. HA's default
  entity context expires after five seconds, so it alone cannot identify an entire
  physical journey.

## Test strategy and known limits

The test suite loads the real integration, config flows, number/sensor platforms,
registry machinery, translations, and cover service in isolated HA instances.
Simulated `CoverEntity` objects record position commands and expose controlled
positions, availability, failures, and action gates. Tests explicitly assert the
absence of unauthorized commands, not just the resulting saved values.

Coverage includes selection, duplicate rejection, independent mappings, initial
values, percentage conversion, buffer boundary cases, endpoints, normalization,
invalid input, offline writes, external motion, restoration, reload, restart into a
fresh HA instance, sensors, action errors and contexts, source renaming/removal,
reconfiguration, listener cleanup, removal, and rapid writes. The fresh-instance
test uses HA's mocked storage and explicitly restores the simulated source registry
snapshot. It is not an operating-system reboot or a physical device test.

Device tests query HA's real WebSocket endpoints for integration filtering and
reciprocal links. They check that manufacturer devices and source entities remain
identical through setup, reload, reconfiguration, and removal, including sources
with identifiers only, connections only, and offline states. They also cover late
device association, changed keys, source removal, child channels, device listener
cleanup, and rejection of older HA versions before any storage or device writes.

Decision tests inspect real Activity events and simulated phone service calls,
including localized values, local time, action context, inclusive buffer boundaries,
fractional positions, endpoint targets, opt-in/out, phone switching, stale notifiers,
push failures, source replacement, independent mappings, entity renames, and excluded
events. Recorder tests retrieve the messages through HA's actual entity and device
Activity queries against isolated SQLite. Successful commands are checked for
localized snapshots, context and rename association, no phone notification, and
logging only after service success, retaining the actual position before dispatch.
No phone receives real messages in tests.

Position tests advance HA timers to exercise reported movement, late final values,
fallback quiet intervals, explicit target precedence, reload during movement,
availability loss, stale callbacks, rename, unload, independent entries, and
persistence failures or source changes during saving. Recorder queries verify
passive alignment in sensor history and its external Activity entries through
entity and virtual-device filters. Attribution tests cover own feedback with motion
states, quiet intervals, child or absent origin contexts, reload during movement,
external interruptions, expired/failed commands, mapping isolation, and removal.

See [Testing](docs/TESTING.md) for commands and
[Repository and HACS maintenance](docs/PUBLISHING.md) for distribution details.
The repository is available for HACS custom installation; an actual HACS download
and remote HACS validation were not performed during local development. Hardware
behavior, browser rendering, and the minimum HA runtime have not been tested.
Source feature declarations and current positions must be trustworthy;
the integration cannot detect firmware or calibration errors.
