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
.venv/bin/python -m compileall -q custom_components tests scripts
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

## Prepared GitHub Actions

Two workflow files carry over the validation jobs from the local Manual Energy
Metering reference's `.github/workflows/validate.yml`:

- [HACS](../.github/workflows/hacs.yml) validates the repository as an integration
  with `hacs/action@main`. It uses the current repository context, so no repository
  name or integration-domain override is needed. PR comments are disabled.
- [Hassfest](../.github/workflows/hassfest.yml) checks out the repository using
  `actions/checkout@v4` and validates its integration with
  `home-assistant/actions/hassfest@master`.

Both retain the reference's triggers: pushes, pull requests, daily at 00:00 UTC,
and manual dispatch. Token permissions are limited to `contents: read`.
They become available after the owner publishes the repository; no GitHub workflow
has been triggered during local development. The existing pytest, Ruff, and local
packaging checks above remain separate from these official validators.

## Manual UI check in a separate HA instance

Copy `custom_components/natural_shutter` into the test instance's configuration
directory and restart it. Merge [the simulated cover example](../examples/simulated_cover.yaml)
into that instance's `configuration.yaml` and restart once more. It creates only
an input-number helper and a template cover; there is no device action.
This YAML is a test fixture, not a requirement for normal Natural Shutter setup.

1. Add Natural Shutter manually and select **Natural Shutter demo**.
2. Confirm target 30%, buffer 0%, and exactly two numbers plus two sensors.
3. Change target to 70%; the simulated HA position helper should become 30%.
4. Change the position helper directly to 45%; the saved target must stay 70%.
5. Set buffer to 10%, change target to 71%, then back to 70%. The source should
   move only when the actual difference meets the threshold.
6. Use the [standard card example](../examples/dashboard.yaml) with the created IDs.
   Confirm slider rendering and the setting sensors in History.
7. Reload and restart: the target must equal 100 minus the simulated source position;
   the buffer and source position must stay unchanged, with no movement command.
8. Rename the source entity ID in its settings; confirm preserved mapping and values.
9. Make the simulated cover unavailable: the target slider must show unavailable,
   while the buffer and history sensors keep their saved values. Restore the source:
   the target must reappear unchanged, without movement or position alignment.
10. Remove the Natural Shutter entry: its entities and settings disappear, while the
   original template cover and helper remain.

Confirm all mappings appear together under **Integrations → Natural Shutter**.
The template demo has no registered actuator device and therefore no device link.
In a separate device-backed test setup, inspect **Linked devices** in both directions
and confirm the actuator retains its name, ownership, and original entities.

Do not run this optional example in a production instance as part of automated tests.
The automated test suite also verifies unavailable/invalid source data, failed
actions, duplicate sources, endpoint buffers, listener cleanup, and concurrent writes.

## Limits of the executed validation

Automated checks run against HA 2026.9.4. Device-link APIs were verified in HA
2026.8.0's official source, but that minimum has not been runtime-tested. The YAML
demo loads and runs in the automated suite; its
interactive browser check remains separate. Browser rendering, physical devices,
actual HACS installation, and official hassfest/HACS validation are checks the
owner can perform later. Results from commands actually executed are recorded in
[Validation](VALIDATION.md).
