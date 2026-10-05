# Local tests

The automated tests use only simulated covers. They do not contact device services,
alter a production HA installation, or move physical shutters.

## Reproduce the checks

Use **Python 3.14** for the pinned test stack (HA 2026.9.4). From the project root:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt
.venv/bin/python -m pytest -q --cov --cov-report=term-missing
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python scripts/validate_project.py
PYTHONPYCACHEPREFIX=/tmp/natural-shutter-compile-cache .venv/bin/python -m compileall -q custom_components tests scripts
```

`requirements.txt` is the original product specification, not a pip dependency list.
Use `requirements_test.txt` for test dependencies. Runtime dependencies are provided
by HA itself; the integration installs no external packages.

Tests load actual HA config flows and entity platforms. Cover actions are traced
by simulated entities. Lifecycle tests use HA's mocked storage and a fresh HA object
for restoration; they do not simulate a complete OS reboot. Recorder behavior is
tested separately with an isolated SQLite database.

Device tests use HA's real WebSocket endpoints to verify integration filtering and
reciprocal Linked devices navigation. Source registry snapshots and device change
events verify that setup, reload, reconfiguration, and removal update only owned
devices. Test source assignments and simulated manufacturer metadata are created
exclusively inside isolated HA fixtures. Older HA versions are rejected before
settings storage or device registration.

## Official validation

Official HACS and Home Assistant `hassfest` validation are separate from the
pytest, Ruff, and local packaging checks above. The current checkout contains no
GitHub Actions workflow files. The earlier workflow-transfer checks are recorded
as development history in [Validation](VALIDATION.md#transferred-github-actions);
they do not document a successful hosted validator run.

## Manual UI check in a separate HA instance

Install Natural Shutter through HACS as a custom repository using the
[README instructions](../README.md#hacs-custom-repository), then restart the test
instance. Alternatively, use the README's manual ZIP installation steps.
Merge [the simulated cover example](../examples/simulated_cover.yaml)
into that instance's `configuration.yaml` and restart once more. It creates only
an input-number helper and a template cover; there is no device action.
This YAML is a test fixture, not a requirement for normal Natural Shutter setup.

1. Add Natural Shutter manually and select **Natural Shutter demo**.
2. Confirm target 30%, buffer 0%, and exactly two numbers plus two sensors.
3. Change target to 70%; the simulated HA position helper should become 30%.
4. Change the position helper directly to 45%; the target initially stays 70%, then
   becomes 55% after ten quiet seconds. The target history sensor must record the
   change without a cover command or phone message. A **Target updated** Activity
   entry must show the external change from 70% to 55%, the HA position 45%, and
   the equivalent position 55%.
5. Set buffer to 10%, change target to 71%, then back to 70%. The source should
   move only when the actual difference meets the threshold.
   For each changed target suppressed by the rule, check **Activity** on the target
   slider and virtual device: verify the reason, old/new target, both position scales,
   distance, buffer, and local timestamp. Successful position commands create a
   **Position command sent** Activity entry without a phone notification, including
   when the difference equals the buffer. An already reached position has its own reason.
6. Use the [standard card example](../examples/dashboard.yaml) with the created IDs.
   Confirm slider rendering and the setting sensors in History.
7. Reload and restart: the target must equal 100 minus the simulated source position;
   the buffer and source position must stay unchanged, with no movement command.
8. Rename the source entity ID in its settings; confirm preserved mapping and values.
9. Make the simulated cover unavailable: the target slider must show unavailable,
   while the buffer and history sensors keep their saved values. Restore the source:
   the saved target must reappear without movement. Change the helper while offline
   and verify that the target adopts its equivalent after the quiet interval.
10. Remove the Natural Shutter entry: its entities and settings disappear, while the
   original template cover and helper remain.

Before removing the entry, optionally use **Configure** to select a Companion App
phone registered with this separate test instance. Trigger a buffered target change
and compare the phone message with Activity. Switch or disable the recipient and
confirm the options take effect without reload, target alignment, or movement.
Activity continues with push disabled. Repeating the same normalized target,
changing only the buffer, external reports, setup, and reload create no suppression
messages. Source validation and cover errors keep their existing error reporting.
Actual phone delivery is a manual check; automated tests register simulated
`notify.mobile_app_*` services and send no real messages.
Also trigger an allowed position command with a phone selected: confirm the
**Position command sent** entry appears in Activity and no phone message is sent.
Its actual position is the snapshot before dispatch. Failed actions do not produce
a success entry; the integration does not confirm physical movement or target arrival.

Use **Configure** to change the quiet interval for a source without movement
states, then verify the new delay. For a source reporting opening/closing, verify
that the target stays unchanged during movement, even after the quiet interval.
After stopping, allow two seconds for final position updates. Reload during a
reported movement must retain the target until stop. Enter a new target while a
previous position is waiting to align and check that old feedback cannot overwrite
it; later position changes may align it normally. Repeat with two mappings to
verify independent timing. A missing or invalid current position must make the
target number unavailable while the buffer and both history sensors remain available.
External changes must create one target-alignment Activity entry only when the
rounded target changes. Own movement feedback must create no additional entry,
including after reload during movement. With a phone selected, neither case sends
a notification. Distinct source user/automation contexts and reverse movement
must override an outstanding own command. Sources without origin metadata cannot
reliably distinguish a manual intervention along an ongoing own movement's path.

Confirm all mappings appear together under **Integrations → Natural Shutter**.
The template demo has no registered actuator device and therefore no device link.
In a separate device-backed test setup, inspect **Linked devices** in both directions
and confirm the actuator retains its name, ownership, and original entities.

Do not run this optional example in a production instance as part of automated tests.
The automated test suite also verifies unavailable/invalid source data, failed
actions, duplicate sources, endpoint buffers, listener cleanup, and concurrent writes.
Suppression tests also check German/English message values, HA-local timestamps,
phone selection and opt-out, missing or failed notification services, recipient
persistence across reload/reconfiguration, action contexts, and target renames.
Position tests advance HA timers without real sleeps and cover late final reports,
rapid event bursts, reload during motion, explicit target precedence, outages,
renames, source removal, unload, storage failures, and source changes during a
passive save. They assert the absence of cover commands and decision notifications.
Recorder queries also verify passive target transitions in real sensor history.
Alignment Activity tests verify German/English message values, local timestamps,
source contexts, target renames, own-command attribution and expiry, failed commands,
external interruptions, independent mappings, removal, and save failures.
The Recorder suite queries command and suppression entries using real Activity entity and
device filters against isolated SQLite; it initializes the processor's filter
configuration directly, without starting the frontend.

## Limits of the executed validation

Automated checks run against HA 2026.9.4. Device-link APIs were verified in HA
2026.8.0's official source, but that minimum has not been runtime-tested. The YAML
demo loads and runs in the automated suite; its
interactive browser check remains separate. Browser rendering, physical devices,
an interactive HACS installation, and official hassfest/HACS validation were not
performed as part of the local checks. The repository is available for HACS custom
installation. Results from commands actually executed are recorded in
[Validation](VALIDATION.md).
