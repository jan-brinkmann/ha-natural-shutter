# Publication preparation

This is a local source tree, not a published GitHub or HACS project. Version
`1.0.0` is the initial source-file version requested in the requirements. No Git
repository was initialized and no remote write, release, tag, or PR was created.
Version changes require an explicit instruction from the owner.

## Configured metadata

At the owner's request, licensing and maintainer metadata follow the existing
Manual Energy Metering and Shelly LED Control repositories. Their locally available
`LICENSE` and integration manifests were consulted.

- Planned repository: `https://github.com/jan-brinkmann/ha-natural-shutter`.
- Documentation: `https://github.com/jan-brinkmann/ha-natural-shutter#readme`.
- Issue tracker: `https://github.com/jan-brinkmann/ha-natural-shutter/issues`.
- Codeowner: `@jan-brinkmann`.
- License: MIT, with `Copyright (c) 2026 Jan Brinkmann and contributors`.

**The repository does not exist yet.** These URLs are configured for its future
publication and are not claims of an accessible repository or issue tracker.
Both READMEs use the planned URL for their future HACS installation instructions.

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

## Remaining publication work

- Create the planned public repository manually and publish the local source when
  ready. Confirm that its README and issue tracker are accessible at the configured URLs.
- Verify the chosen HACS validation version's local-brand support before submission.
- Add a repository description, topics, and an enabled issue tracker when publishing.

This remaining publication work does not prevent local manual installation.

## Prepared layout

There is exactly one integration directory under `custom_components/`; all runtime
code and translations are inside it. The manifest includes version, config flow,
cover dependency, device classification, calculated IoT class, and empty external
requirements. `hacs.json` supplies the display name, minimum HA version, and README
rendering. The repository also contains user documentation in two languages,
architecture, tests, examples, and an initial local changelog.

The HACS and Hassfest jobs from Manual Energy Metering's local `validate.yml` are
prepared as `.github/workflows/hacs.yml` and `.github/workflows/hassfest.yml`.
They run on pushes, pull requests, a daily schedule, or manual dispatch after
publication. Both use `contents: read`; HACS PR comments are disabled. They select
the current repository automatically and need no hardcoded owner or domain change.
See [Testing](TESTING.md#prepared-github-actions) for details.

## Owner's later validation

Run the [local checks](TESTING.md), finish repository setup, and validate with the
official HA `hassfest` and HACS validation tools in an isolated checkout/environment.
After publishing the workflow files, review their results in the repository's
Actions tab; no successful hosted validation has been claimed locally.
Install the published repository as a HACS **custom repository** and confirm setup,
translations, sliders, integration grouping, reciprocal device links, updates, and
removal in a test HA instance. The local
validator checks packaging and translation consistency; it is not an official
HACS or hassfest certification.

HACS can use a repository's default branch when there are no releases. Default-store
inclusion has separate review requirements. Release and repository management remain
manual responsibilities of the owner; this document does not authorize Codex to
perform any Git or GitHub writes.

Official references:

- [HACS integration requirements](https://www.hacs.dev/docs/publish/integration/)
- [HACS repository metadata](https://hacs.dev/docs/publish/start/)
- [HACS default-store review](https://hacs.dev/docs/publish/include/)
- [HA manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [HA brand images](https://developers.home-assistant.io/docs/core/integration/brand_images/)
