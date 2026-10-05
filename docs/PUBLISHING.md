# Repository and HACS maintenance

Natural Shutter is available from
[jan-brinkmann/ha-natural-shutter](https://github.com/jan-brinkmann/ha-natural-shutter)
and can be installed through HACS as a **custom repository**. The owner has
completed repository creation. Installation instructions are in the
[English README](../README.md#installation) and
[German README](../README.de.md#installation).

The integration version is `1.0.0`. Version changes require an explicit instruction
from the owner.

## Configured metadata

At the owner's request, licensing and maintainer metadata follow the existing
Manual Energy Metering and Shelly LED Control repositories. Their locally available
`LICENSE` and integration manifests were consulted.

- Repository: `https://github.com/jan-brinkmann/ha-natural-shutter`.
- Documentation: `https://github.com/jan-brinkmann/ha-natural-shutter#readme`.
- Issue tracker: `https://github.com/jan-brinkmann/ha-natural-shutter/issues`.
- Codeowner: `@jan-brinkmann`.
- License: MIT, with `Copyright (c) 2026 Jan Brinkmann and contributors`.

Both READMEs use this repository URL for HACS installation and manual ZIP downloads.
The integration manifest already contains the matching documentation and issue
tracker URLs.

## HACS distribution

Users add `https://github.com/jan-brinkmann/ha-natural-shutter` in **HACS → ⋮ →
Custom repositories**, select **Integration**, and click **Add**. They can then
find **Natural Shutter** in HACS, download it, and fully restart Home Assistant
before adding the integration under **Settings → Devices & services**.

GitHub releases are optional. Without releases, HACS downloads files from the
repository's default branch. Default-store inclusion is a separate submission and
review process; custom repository installation does not require it.

## Included images

The owner's `docs/banner.png` is displayed directly below the title in both READMEs,
using the same centered, full-width layout as Manual Energy Metering.

The owner's square PNG icon is included at
`custom_components/natural_shutter/brand/icon.png`. HA 2026.3 and newer automatically
discover local integration brand images in this directory; no manifest field or
custom icon-serving code is required. Copy the complete integration directory when
installing manually. HA also uses the icon as the fallback for logo, dark-mode, and
high-resolution image requests. The supplied image files are preserved unchanged.

The integration requires HA 2026.8.0 for device linking without changes to source
devices. All supported versions discover the bundled icon locally.

## Repository layout

There is exactly one integration directory under `custom_components/`; all runtime
code and translations are inside it. The manifest includes version, config flow,
cover dependency, device classification, calculated IoT class, and empty external
requirements. `hacs.json` supplies the display name, minimum HA version, and README
rendering. The repository also contains user documentation in two languages,
architecture, tests, examples, and a changelog.

## Maintenance and validation

Run the [local checks](TESTING.md) after source changes. Official HA `hassfest` and
HACS validation are separate checks; the local validator checks packaging and
translation consistency. The current checkout contains no GitHub Actions workflow
files. Earlier workflow-transfer work is recorded as development history in
[Validation](VALIDATION.md#transferred-github-actions).

For an installation check, use a separate HA instance with HACS and confirm the
download, setup, translations, sliders, integration grouping, reciprocal device
links, updates, and removal. The [simulated-cover example](TESTING.md#manual-ui-check-in-a-separate-ha-instance)
can be used without physical hardware. An interactive HACS installation and hosted
validator runs were not performed as part of the local documentation update.

Repository settings, source publication, releases, and default-store submission
remain manual responsibilities of the owner. This document does not authorize
Codex to perform Git or GitHub writes.

Official references:

- [HACS custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/)
- [HACS integration requirements and optional releases](https://www.hacs.xyz/docs/publish/integration/)
- [HACS repository metadata](https://www.hacs.xyz/docs/publish/start/)
- [HACS default-store review](https://www.hacs.xyz/docs/publish/include/)
- [HA manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [HA brand images](https://developers.home-assistant.io/docs/core/integration/brand_images/)
