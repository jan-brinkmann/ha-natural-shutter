[Deutsche Dokumentation](README.de.md)

# Natural Shutter

<p align="center">
  <img
    src="docs/banner.png"
    alt="Natural Shutter banner"
    width="100%"
    style="display: block; width: 100%; background-color: #ffffff;"
  >
</p>

Natural Shutter adds a saved target position and a movement buffer to your existing
Home Assistant shutters, including position-capable covers from Homematic IP,
Shelly, and other integrations.

## Features

- Add each shutter manually in Home Assistant; nothing is discovered automatically.
- Two independent sliders per shutter: **Target position** and **Buffer**.
- Two numeric history sensors: **Target position history** and **Buffer history**.
- On startup and reload, the target adopts the actual position without movement;
  the buffer is retained.
- German and English setup, entity names, and action error messages.
- Existing cover entities and their manufacturer integrations remain in use.
- Target slider availability follows the source cover; reconnection causes no movement.
- All added shutters appear under **Natural Shutter** in the **Integrations** tab.
- Reciprocal **Linked devices** navigation between each virtual device and its actuator.
- Activity entries for sent position commands and targets suppressed by the
  position/buffer rule; optional phone notifications for suppressed movement.

## Target position and buffer

**Target position:** 0% means fully open, 100% fully closed. It records your last
setting between integration loads. A wall switch, manufacturer app, Alexa, the
original HA cover, or another automation can move the shutter without changing this
saved target until the next load.

**Buffer:** the minimum difference in **percentage points** between the actual
position and the requested position. Movement occurs only when you explicitly
change the target, the shutter is away from that target, and the difference is at
least the buffer. A buffer of 0 allows every changed target with a different actual
position to send a command. Changing the buffer itself never causes movement.

Both sliders use 0–100%, step 1. Decimal action inputs are rounded to whole
percentages (a half rounds up); invalid or out-of-range values are rejected.

### Example

Change the target to **70%** with a **10%** buffer. Natural Shutter requests
**30%** on the original HA cover, whose scale is 0% closed and 100% open.

| Actual HA position | Difference | Result |
| --- | --- | --- |
| 45% | 15 points | Move to 30% |
| 40% | 10 points | Move to 30% |
| 35% | 5 points | Save the target; stay put |
| 30% | 0 points | Stay put |
| 20% | 10 points | Move to 30% |
| 15% | 15 points | Move to 30% |

The same rule applies to fully open and fully closed targets.

## Installation

Requires **Home Assistant 2026.8.0 or newer** and a cover that supports absolute
position commands. Device links rely on HA 2026.8's separation of devices owned by
different integrations; older versions are rejected before settings or devices
are changed. The automated tests use HA 2026.9.4; the minimum version's registry
APIs were checked, but its full runtime has not been tested. The bundled integration
icon is displayed automatically.

### HACS custom repository

Natural Shutter is available through HACS as a custom repository from
[jan-brinkmann/ha-natural-shutter](https://github.com/jan-brinkmann/ha-natural-shutter).
HACS must already be installed and configured in Home Assistant.

1. Open **HACS → ⋮ → Custom repositories**.
2. Enter `https://github.com/jan-brinkmann/ha-natural-shutter` and select **Integration**.
3. Click **Add** and close the custom repositories dialog.
4. Search for **Natural Shutter** in HACS, open it, and click **Download**.
5. Fully restart Home Assistant.
6. Follow the setup instructions below to add your shutters.

See the [official HACS instructions](https://www.hacs.xyz/docs/faq/custom_repositories/)
for adding custom repositories. [GitHub releases are optional](https://www.hacs.xyz/docs/publish/integration/):
without releases, HACS downloads the repository's default branch.

### Manual installation

1. Download and extract the [repository ZIP](https://github.com/jan-brinkmann/ha-natural-shutter/archive/HEAD.zip).
2. Copy the complete `custom_components/natural_shutter` folder into
   `<configuration_directory>/custom_components/natural_shutter` (usually `/config`
   on Home Assistant OS).
3. Check that `manifest.json` is directly inside that folder.
4. Fully restart Home Assistant and follow the setup instructions below.

### Updates

Download available updates through HACS and fully restart Home Assistant. For a
manual installation, replace the integration folder with the updated copy and
restart. Existing entries can be retained: at load, the target adopts the current
source position without movement and the saved buffer is retained.

## Setup and daily use

1. Open **Settings → Devices & services → Add integration → Natural Shutter**.
2. Select an existing cover. Optionally enter a distinguishable name.
3. Repeat for each additional shutter. Each entry gets its own virtual device and
   four entities; duplicate sources are rejected.

Find all entries together under **Settings → Devices & services → Integrations →
Natural Shutter**. On a virtual device's page, **Linked devices** opens the actuator
device provided by Shelly, Homematic IP, or another source integration. The actuator's
page links back to Natural Shutter as well. Only the virtual device's identifiers
and connections are supplemented; the actuator's metadata, ownership, and entities
are untouched. Links follow source device reassignment and reconfiguration without
movement. Existing entries acquire the links after a full HA restart following
the integration update; they do not need to be added again.

If the source cover has no registered device, there is no actuator device to link.
For a cover represented as a child channel device, the link opens its parent
actuator: HA's **Linked devices** list supports main devices.

The initial buffer is **0%**. Each time the integration loads, including startup and
reload, the target is set to **100 minus the source cover's current HA position**,
rounded to whole percentages. This is saved without sending a movement command,
regardless of the buffer. The saved buffer is retained.

If no valid live position is available at load, the saved target is retained. A new
mapping uses the position captured during selection as a fallback, or 0% if that
position was also unavailable. Later position reports and reconnections do not change
the target; another load or an explicit slider change is required.

Adjust the sliders on the device page or a standard dashboard card. Automations
can use `number.set_value` on the target slider. Find your exact entity IDs on the
device page; IDs depend on language and any names you have chosen.

```yaml
service: number.set_value
target:
  entity_id: number.living_room_target_position  # Replace with your entity ID.
data:
  value: 70
```

Use **Reconfigure** on an entry's menu to rename it or explicitly replace a missing
source. Reconfiguration reloads the entry: the buffer is retained and the target
adopts the current source position if valid, without movement. Target and buffer
remain adjustable directly through their sliders.

### Understand position decisions

When you change the normalized target and the existing position/buffer rule prevents
a position command, an **Activity** entry appears for the target slider and its
virtual Natural Shutter device. The message distinguishes **Difference below buffer**
from **Already at the requested position**. The new target remains saved.

When the integration issues a position command, it also creates a **Position command
sent** entry after `cover.set_cover_position` returns successfully. This entry
contains the same values, using the actual position before dispatch. It never
sends a phone notification. It confirms the successful action call; physical travel
and reaching the target position remain unmonitored.

To receive suppressed-movement messages on your phone, open **Settings → Devices & services →
Natural Shutter → Configure** for the desired shutter entry. Select the phone's
`notify.mobile_app_…` service under **Phone notification service**. The phone must
be registered with your HA instance through the Companion App and allow notifications;
the app provides its own
[notification service](https://companion.home-assistant.io/docs/notifications/notifications-basic/).
With no registered phones, the only choice is **Push notifications disabled**.
Push is disabled initially and can be enabled, switched, or disabled independently
for each shutter. Changes apply immediately without reload, position alignment,
or movement. Activity entries are also created when push is disabled.

Activity entries and suppression messages contain the date and time in HA's configured time zone, including
the UTC offset, shutter name and source entity ID, previous and new targets,
actual position on both scales, HA target, difference, and buffer in percentage
points (`pp`). Messages follow HA's configured language (German or English,
with English fallback).

Example: change the target from 30 to 70%, with actual HA position 35% and buffer 10 pp:

```text
Living room: No movement
2026-10-05 14:34:56+02:00 · cover.living_room: Difference below buffer.
Target 30 → 70 %, actual 65 % (HA 35 %), HA target 30 %, difference 5 pp, buffer 10 pp.
```

A difference equal to the buffer still sends a command and creates a **Position
command sent** entry. Setting the same normalized target, buffer changes, external
movement, startup, and reload create no position-decision entries or phone messages.
Unavailable sources, invalid
positions, and failed cover actions retain their existing action errors and log
messages. Later physical movement or position feedback is not monitored.

Viewing these entries requires HA **Activity/Logbook** and **Recorder**; their filters
and retention also apply to these entries. A standard dashboard can display them
with the Activity card in the example linked below. If the selected phone service
is missing or a push fails, the Activity entry is retained and HA logs the notification
failure. The target and movement decision are preserved; there is no automatic retry.

See [standard dashboard examples](examples/dashboard.yaml),
[local test instructions](docs/TESTING.md), and [Architecture](ARCHITECTURE.md).

## Behavior and limits

- Installation, startup, reload, restoring values, reconnection, external movement,
  sensor updates, buffer changes, and setting the same normalized target cause no
  movement. There is no automatic correction of a saved target.
- The target slider is unavailable when its source is missing, unknown, unavailable,
  disabled, or only a restored placeholder. Offline target actions are skipped by HA
  without saving a new value. Once the source returns, the saved target reappears
  without movement or alignment. The buffer and history sensors remain available.
- If the source loses availability while an accepted target write is being saved,
  or has an invalid actual position, the new target remains saved and the skipped
  action is reported in the UI/action trace and HA logs. Nothing is queued. A failed
  cover action also retains the target and is never automatically retried. To try
  again, explicitly select a different target when the source is available.
- A source with a stable registry identity can be renamed. Sources without that
  identity require manual reconfiguration after an Entity-ID rename.
- The two history sensors track settings, including targets that did not cause
  movement. History availability and retention depend on your **Recorder** settings
  and filters; no independent archive or long-term statistics are created.
- Calibration, travel direction, movement progress, and device communication remain
  responsibilities of the source integration. No real hardware tests have been run.

## Removal

Remove the desired entry under **Settings → Devices & services → Natural Shutter**.
Only that mapping's four entities and saved settings are removed. The source cover
and other mappings remain. Existing Recorder history follows Recorder's retention.
After removing all entries, uninstall through HACS or remove the integration folder
manually, then restart Home Assistant.

## License

This project is licensed under the [MIT License](LICENSE).
Copyright (c) 2026 Jan Brinkmann and contributors.
