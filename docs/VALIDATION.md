# Executed validation

Validated locally on **2026-10-04**. No physical devices, production HA instance,
Git metadata, or GitHub state were changed.

The owner has since created
[jan-brinkmann/ha-natural-shutter](https://github.com/jan-brinkmann/ha-natural-shutter),
which is available for installation through HACS as a custom repository. The
sections below record development history; references to publication preparation
describe the repository's state at those earlier stages.

## Environment

- Python 3.14.4
- Home Assistant 2026.9.4
- pytest-homeassistant-custom-component 0.13.367
- pytest 9.0.3
- Ruff 0.16.10

An already available isolated test environment was used at
`/tmp/shelly-led-night-mode-venv`. Its interpreter and tools ran against this source
tree. All device commands in the tests targeted simulated entities or the
hardware-free template-cover example.

## Initial implementation results

| Executed command | Result |
| --- | --- |
| `/tmp/shelly-led-night-mode-venv/bin/python -m pytest -q --cov --cov-report=term-missing` | **97 passed**, 5.66 seconds |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff check .` | Passed |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff format --check .` | Passed; 24 Python files formatted |
| `python3 scripts/validate_project.py` | Passed; remaining publication metadata reported explicitly |
| `python3 -m compileall -q custom_components tests scripts` | Passed |

Coverage reports **100%** for the integration's 290 statements and 54 measured
branches. Coverage describes exercised code paths and does not certify hardware
behavior, browser rendering, or compatibility with every HA version.

The suite explicitly checks that setup, initialization, repeated normalized values,
buffer changes, source feedback, external movement, restoration, reload, restart,
reconnection, sensor updates, registry identity changes, and removal do not dispatch
unauthorized position commands. It also exercises conversion and buffer boundaries,
saved skipped/failed targets, ordered rapid writes, independent mappings, action
contexts, invalid input/storage, listener cleanup, and duplicate flows.

The Recorder test queried saved sensor transitions from isolated SQLite. The YAML
demo was loaded by HA and exercised through input-number actions; the dashboard
example was checked structurally. An interactive browser check has not been run.

## Added files

- Integration: `custom_components/natural_shutter/__init__.py`, `const.py`,
  `source.py`, `controller.py`, `config_flow.py`, `entity.py`, `number.py`, `sensor.py`,
  `manifest.json`, `strings.json`, `translations/en.json`, and `translations/de.json`.
- Tests: `tests/__init__.py`, `conftest.py`, `test_config_flow.py`, `test_commands.py`,
  `test_lifecycle.py`, `test_entities.py`, `test_recorder.py`, and `test_examples.py`.
- Project metadata and tooling: `.gitignore`, `hacs.json`, `pyproject.toml`,
  `requirements_test.txt`, and `scripts/validate_project.py`.
- Documentation: `README.md`, `README.de.md`, `ARCHITECTURE.md`, `CHANGELOG.md`,
  `docs/PUBLISHING.md`, `docs/TESTING.md`, and this `docs/VALIDATION.md`.
- Examples: `examples/dashboard.yaml` and `examples/simulated_cover.yaml`.

The pre-existing `requirements.txt` and `AGENTS.md` were preserved. The initially
empty `LICENSE` was subsequently completed at the owner's request; see below.
There was no Git repository at the start; none was initialized. All source changes
remain local and unstaged.

## Licensing and repository metadata update

On 2026-10-04, the owner authorized using the reference repositories' license,
codeowner, and GitHub owner for the planned `ha-natural-shutter` repository.
The complete MIT license matches both locally available reference `LICENSE` files,
including `Copyright (c) 2026 Jan Brinkmann and contributors`.

Changed files: `LICENSE`, `custom_components/natural_shutter/manifest.json`,
`README.md`, `README.de.md`, `ARCHITECTURE.md`, `docs/PUBLISHING.md`, and
`docs/VALIDATION.md`. The integration version remains `1.0.0`.

Checks performed after the metadata update:

- `/tmp/shelly-led-night-mode-venv/bin/python -m pytest -q`: **97 passed**, 5.48 seconds.
- `python3 scripts/validate_project.py`: passed; only brand imagery remains flagged.
- `/tmp/shelly-led-night-mode-venv/bin/python -m ruff check .`: passed.
- `/tmp/shelly-led-night-mode-venv/bin/python -m ruff format --check .`: passed.
- A local Python comparison confirmed both reference licenses match exactly, the
  expected codeowner and planned documentation/issue URLs are configured, both
  READMEs use the planned repository URL, and the version has not changed.

At that stage, the repository had not been created. Documentation identified the
URLs as future publication addresses; no Git or GitHub write operations were
performed. Repository creation has since been completed by the owner.

## Target alignment on integration load

At the owner's request on 2026-10-04, each entry load now aligns the saved target
with the valid live source position: `target = round_half_up(100 - current_position)`.
This replaces unconditional restoration of the target with non-actuating alignment
at load. The buffer remains saved. If the live position is missing, unknown,
unavailable, invalid, or only a restored placeholder, the saved target remains.
A new mapping retains its selection snapshot or zero as an offline fallback.
Later source reports and reconnection do not align the target or send a command.

The alignment runs before entity setup, without invoking the target setter or
command dispatcher, and saves new or changed values. Tests exercise endpoints,
fractional rounding, different buffers including zero, startup into a fresh HA
instance, reload, reconfiguration, delayed setup, missing/invalid/restored source
states, renamed sources, and removed registry identities with reused entity IDs.
They assert that the source position remains unchanged and no command is sent.

Changed files:

- `custom_components/natural_shutter/controller.py`, `__init__.py`, and `config_flow.py`.
- `custom_components/natural_shutter/strings.json`, `translations/en.json`, and
  `translations/de.json`.
- `tests/test_config_flow.py` and `tests/test_lifecycle.py`.
- `README.md`, `README.de.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/TESTING.md`,
  and `docs/VALIDATION.md`.

Checks after the target-alignment change:

| Executed command | Result |
| --- | --- |
| `/tmp/shelly-led-night-mode-venv/bin/python -m pytest -q --cov --cov-report=term-missing` | **111 passed**, 6.40 seconds |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff check .` | Passed |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff format --check .` | Passed; 25 Python files formatted |
| `python3 scripts/validate_project.py` | Passed; only brand imagery remains flagged |
| `python3 -m compileall -q custom_components tests scripts` | Passed |

Integration coverage is **100%** for 295 statements and 58 measured branches.
The integration version remains `1.0.0`. All changes remain local and unstaged.

## Source availability propagation

At the owner's subsequent request, the target slider now becomes unavailable when
its resolved source is missing, unknown, unavailable, disabled, or a restored
placeholder. HA skips actions on the unavailable target number without changing
the saved value. The buffer and both setting-history sensors remain available.
When the source returns, the saved target is displayed again without movement or
position alignment. Load-time alignment remains as described above.

A source state listener publishes availability transitions only. Registry events
rebind this listener after a rename or detach it after source removal. Both source
and registry listeners are removed on unload or failed setup; late callbacks cannot
reattach listeners. Registry-pinned mappings refuse to use unrelated reused IDs.

Tests cover initial offline setup, runtime outages, missing and unknown states,
restored placeholders, disabled sources, source renames/removal, reload cleanup,
independent mappings, skipped offline actions, and a source disappearing during an
accepted target write's save. The last case retains the accepted target and reports
the skipped dispatch without any replay. Commands only targeted simulated covers.

Changed files:

- `custom_components/natural_shutter/controller.py`, `number.py`, `entity.py`, and
  `sensor.py`.
- `tests/test_entities.py`, `tests/test_commands.py`, and `tests/test_lifecycle.py`.
- `README.md`, `README.de.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/TESTING.md`,
  and `docs/VALIDATION.md`.

Latest checks after availability propagation:

| Executed command | Result |
| --- | --- |
| `/tmp/shelly-led-night-mode-venv/bin/python -m pytest -q --cov --cov-report=term-missing` | **122 passed**, 7.03 seconds |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff check .` | Passed |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff format --check .` | Passed; 25 Python files formatted |
| `python3 scripts/validate_project.py` | Passed; only brand imagery remains flagged |
| `python3 -m compileall -q custom_components tests scripts` | Passed |

Integration coverage is **100%** for 334 statements and 74 measured branches.
Version `1.0.0` and repository metadata are unchanged. No Git or GitHub writes were
performed; all changes remain local and unstaged.

## Supplied banner and integration icon

The owner added `docs/banner.png` and
`custom_components/natural_shutter/brand/icon.png`. Both READMEs now display the
banner immediately below the main title, with the same centered, full-width HTML
layout as the local Manual Energy Metering reference. The language link appears
above the title, matching that reference's ordering.

The icon already occupies HA's supported local brand-image path. Its discovery
requires no new manifest key, runtime code, or custom HTTP endpoint. Local icons
are supported from HA 2026.3; the then-supported earlier versions used the external
brands repository. The current minimum is 2026.8.0; see the device-link update below.
The supplied PNG bytes were not modified.

Executed checks:

- A one-off Python/Pillow check verified both PNGs and README placement. The banner
  is 2079 × 756 pixels; the square icon is 1254 × 1254 pixels.
- A one-off check using HA 2026.9.4's real loader and local brands response handler
  verified automatic discovery and successful `image/png` responses matching the
  supplied icon byte for byte. All eight icon/logo, light/dark, and resolution
  variants resolved successfully. This used a temporary configuration, local files
  only, and no frontend browser or network request.
- `python3 scripts/validate_project.py`: passed, with no missing-brand warning.
- `/tmp/shelly-led-night-mode-venv/bin/python -m ruff check .`: passed.
- `/tmp/shelly-led-night-mode-venv/bin/python -m ruff format --check .`: passed.
- `python3 -m compileall -q custom_components tests scripts`: passed.

Image fingerprints:

- Banner SHA-256: `4ff7b6c117154ce699aab78fc867f357c826cec1253f75a7d44e6c06f6f6571a`.
- Icon SHA-256: `e8babf83654b27c0fe3479c32306796577c524e5047a3c4d6d3ef9e934893248`.

Changed files: `README.md`, `README.de.md`, `ARCHITECTURE.md`, `CHANGELOG.md`,
`docs/PUBLISHING.md`, and `docs/VALIDATION.md`. The integration's version and runtime
code remain unchanged, and no Git or GitHub write operations were performed.

## Transferred GitHub Actions

The local Manual Energy Metering reference contains one workflow file,
`.github/workflows/validate.yml`, with HACS and Hassfest jobs. These jobs were
prepared during an earlier development stage as two workflow files for Natural Shutter:
`.github/workflows/hacs.yml` and `.github/workflows/hassfest.yml`.
These files are absent from the current checkout; this section records the earlier
transfer and its checks.

Both preserve pushes, pull requests, the daily 00:00 UTC schedule, manual dispatch,
Ubuntu runners, and `contents: read` permissions. The source action references are
retained. HACS uses `category: integration` and `comment: false`, disabling its
default PR comments. The actions use the current repository/integration context,
so no Manual Energy Metering owner or domain is hardcoded. The Hassfest job is
otherwise identical to the reference.

Executed checks:

- A one-off Python/PyYAML check parsed both workflow documents, verified triggers
  and read-only token permissions against the reference, checked the transferred
  jobs and HACS inputs, and ruled out stale source-domain references.
- `python3 scripts/validate_project.py`: passed.
- `/tmp/shelly-led-night-mode-venv/bin/python -m ruff check .`: passed.
- `/tmp/shelly-led-night-mode-venv/bin/python -m ruff format --check .`: passed.

The HACS action's documented `comment` input and the official workflow usage were
checked. Hosted HACS/Hassfest validation and GitHub workflow dispatch were not run.
The repository was still awaiting creation by the owner at that stage. Python
runtime code and the integration version were not changed.

Added files: `.github/workflows/hacs.yml` and `.github/workflows/hassfest.yml`.
Updated documentation: `docs/TESTING.md`, `docs/PUBLISHING.md`, and
`docs/VALIDATION.md`. All changes remain local and unstaged.

## Integration grouping and reciprocal actuator links

The manifest now declares `integration_type: device`, which makes all Natural
Shutter config entries appear together in the Integrations tab. Each mapping keeps
its own virtual device and four entities. Existing mappings require a full HA
restart after updating the integration files; adding them again is unnecessary.

The new `ShutterDeviceLink` copies the source device's identifiers and connections
onto the owned virtual device while retaining its stable Natural Shutter identifier.
HA discovers reciprocal Linked devices entries from these shared keys. Device
ownership, names, metadata, and source entities in manufacturer integrations are
never changed. Source device reassignment, changed keys, late device association,
removal, and reconfiguration update the owned device's link without saving settings
or sending movement commands. Offline sources retain their device links. Sources
without a registered device have no link; child-channel devices link to their parent
actuator because HA's Linked devices endpoint supports main devices.

The minimum HA version is now **2026.8.0**, when device identities became unique per
config entry. The official 2026.8.0 source was checked for scoped device lookup and
the reciprocal-link API. Setup rejects older versions with a translated error before
loading settings or accessing devices, including manual installations. Tests
simulate older versions to verify this guard; the actual minimum runtime has not
been installed or run. The full suite continues to use HA 2026.9.4.

New tests query HA's actual WebSocket endpoints for integration filtering and Linked
devices in both directions. They exercise sources with identifiers only, connections
only, both keys, and offline states. During setup, reload, and removal, recorded device
registry events identify only the owned virtual device as changed. Complete source
device snapshots and source entity object identities remain unchanged. Other tests
cover reconfiguration, source reassignment, changed identifiers/connections, removed
registry identities with reused entity IDs, child channels, and listener cleanup
after unload and failed setup. Every device-link scenario asserts no cover commands.

Changed or added files:

- Runtime: `custom_components/natural_shutter/device.py` (new), `__init__.py`,
  `controller.py`, `const.py`, and `manifest.json`.
- Translations: `custom_components/natural_shutter/strings.json`,
  `translations/en.json`, and `translations/de.json`.
- Tests and validation: `tests/test_devices.py` (new), `tests/test_lifecycle.py`,
  and `scripts/validate_project.py`.
- Metadata and documentation: `hacs.json`, `README.md`, `README.de.md`,
  `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/PUBLISHING.md`, `docs/TESTING.md`, and
  `docs/VALIDATION.md`.

Executed checks:

| Executed command | Result |
| --- | --- |
| `/tmp/shelly-led-night-mode-venv/bin/python -m pytest -q --cov --cov-report=term-missing` | **137 passed**, 8.41 seconds |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff check .` | Passed |
| `/tmp/shelly-led-night-mode-venv/bin/python -m ruff format --check .` | Passed; 27 Python files formatted |
| `python3 scripts/validate_project.py` | Passed |
| `python3 -m compileall -q custom_components tests scripts` | Passed |

Integration coverage is **100%** for 394 statements and 90 measured branches.
The integration version remains `1.0.0`. No interactive frontend or physical
actuator test was performed. All changes remain local and unstaged; no Git or
GitHub state was changed.

## Repository creation and HACS documentation

On 2026-10-04, the owner reported that the GitHub repository had been created.
The configured Git remote matches `jan-brinkmann/ha-natural-shutter`. Both READMEs
now describe HACS custom repository installation, manual ZIP installation, and
updates. Repository maintenance, testing, architecture, and changelog documentation
reflect this state. The original `requirements.txt` specification has a current
status note while retaining its historical instructions.

References to absent workflow files were corrected in the current instructions;
the earlier validation history is preserved. The integration manifest and
`hacs.json` already contain the matching metadata and needed no changes.

Changed files: `README.md`, `README.de.md`, `ARCHITECTURE.md`, `CHANGELOG.md`,
`docs/PUBLISHING.md`, `docs/TESTING.md`, `docs/VALIDATION.md`, and `requirements.txt`.

Executed checks:

- `python3 scripts/validate_project.py`: passed.
- A one-off Python documentation check: passed; 31 local links/images and heading
  anchors, bilingual HACS instructions, current repository status, manifest URLs,
  minimum HA version, and unchanged integration version were checked.
- `git -c core.whitespace=cr-at-eol diff --check`: passed; the check accounts for
  the original specification's CRLF line endings without changing Git configuration.
- Official HACS custom repository and integration documentation was consulted.

This update changes documentation only. Runtime code, version `1.0.0`, and minimum
HA version `2026.8.0` are unchanged. No interactive HACS installation or hosted
validator run was performed. All changes remain uncommitted and unstaged; no Git
metadata or GitHub state was changed.

## Remaining validation limits

- HA 2026.8.0 provides the required device isolation APIs; the actual minimum
  runtime has not been tested. Full automated checks use HA 2026.9.4.
- Physical hardware, a production HA installation, interactive frontend rendering,
  a full OS restart, actual HACS installation, and official hassfest/HACS validation
  were not exercised.
- The requested README references and official HA/HACS documentation were reachable
  and consulted; links are collected in [Architecture](../ARCHITECTURE.md).
- MIT licensing, codeowner `@jan-brinkmann`, and the repository, documentation, and
  issue URLs are configured. The owner has created the GitHub repository, making
  custom repository installation through HACS available. This local validation
  record does not include an interactive HACS download or hosted validator results.
  See [Repository and HACS maintenance](PUBLISHING.md).

For reproducible installation and checks, see [Testing](TESTING.md) and the
[German installation guide](../README.de.md).
