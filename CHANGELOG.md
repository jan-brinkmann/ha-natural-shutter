# Changelog

## 1.0.0

Initial version, available through HACS as a custom repository.

- Manual selection of existing position-capable covers with duplicate prevention.
- Independent persistent target and buffer sliders per shutter.
- Inverted target scale and inclusive minimum deviation buffer.
- Target alignment with the live source position at each load without movement;
  the buffer and offline fallback target remain saved.
- Commands only on explicit changes of the normalized target.
- Source-dependent target availability, with saved values retained and no movement
  on reconnection; buffer and history sensors remain available.
- Numeric setting history sensors, English and German translations.
- Registry-aware renames, explicit reconfiguration, and individual removal.
- All mappings grouped under Natural Shutter in the Integrations tab.
- Reciprocal actuator links maintained exclusively on the virtual device, including
  source device changes and reconfiguration; requires HA 2026.8.0 or newer.
- Error reporting without queued movements or automatic retries.
- Simulated-cover tests, dashboard examples, and installation documentation.
- HACS custom repository installation, manual ZIP installation, and update instructions
  for `jan-brinkmann/ha-natural-shutter`.
- README banners and a bundled integration icon for HA 2026.3+.
