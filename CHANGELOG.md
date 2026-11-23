# Changelog

All notable changes to Wago2HAddon are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project follows [semantic versioning](https://semver.org/).

> **Version numbering.** Releases up to 0.0.9 were first published with `1.0.x`
> version numbers in `manifest.json` (1.0.0 … 1.0.9, plus 1.0.8.1). They were
> renumbered `0.0.x` to match the GitHub release tags; the content is unchanged.

## [0.1.0] - 2026-11-23

### Added
- **Reconfigure** (⋮ → Reconfigure on the integration) to change the PLC IP
  address. Entities keep their `entity_id`, names, areas and history: their
  unique IDs and the device are migrated to the new address.
- **Automatic clean-up of stale entities.** At startup, entities that the
  Calaos `io.xml` no longer produces (IO point deleted or disabled, or output
  that changed platform such as the old `light.*` entities left over by 0.0.6)
  are removed from the entity registry. The clean-up only runs after a
  successful, non-empty import: a missing or unreadable file never removes
  anything.
- **KNX outputs** (750-849 with KNX/TP1 module, `knx="true"` in `io.xml`) are now
  addressed like Calaos does (+6144, without the 750-8xx offset). They were
  written to a wrong address before.
- **Continuous integration** (GitHub Actions): hassfest, HACS validation, ruff,
  and unit tests for the Modbus client, the click decoder, the `io.xml` import
  and the address translation.

### Changed
- **The integration no longer starts if the UDP port (4646) cannot be bound.**
  Without that socket no heartbeat can be sent, so the PLC resumed its internal
  program while Home Assistant was also driving the outputs. The setup now fails
  with a clear message ("UDP port 4646 is already in use…") and Home Assistant
  retries automatically. This typically happens when a Calaos server is still
  running.
- **Faster startup when the PLC is offline.** Initial reads are no longer
  attempted one entity after the other while the PLC is unreachable (each one
  waited for a connection timeout, which could delay Home Assistant's startup by
  minutes). Relays and inputs get their real state from the resynchronisation
  run as soon as the PLC comes back; DALI lights and analog sensors do their
  first read at that moment.
- **Shutters: 0.5 s pause before reversing the motor.** Going straight from "up"
  to "down" (or back) stresses the motor and the relay contacts; both coils now
  stay off for at least 0.5 s on a direction change.
- **Shutters: the position is published about once a second** while moving
  (instead of 5 times a second), which divides the recorder writes by five. The
  position is still computed every 0.2 s, so stops remain precise.
- The PLC IP address is no longer part of the options (⋮ → Configure): use
  Reconfigure, which migrates the entities. An address previously changed in
  the options is moved over automatically, with no change to the entities.
- The *Calaos program version* on the device page is now updated when it becomes
  known after startup (e.g. PLC offline when Home Assistant started).
- Minimum Home Assistant version raised to 2024.4 in `hacs.json` (already
  required by the config flow).

- `LICENSE` now holds the full GPLv3 text (so GitHub and HACS recognise it);
  the project notice moved to `NOTICE`.

### Removed
- The "750-8xx family" option. It was never used: the address offset of every
  output comes from its own `wago_841` attribute in `io.xml` (default `true`).
  Existing configurations keep working; the stored value is simply ignored.

## [0.0.9] - 2026-10-01

### Security
- **UDP messages are authenticated by source address.** The listener on port
  4646 accepted `WAGO INT` messages from any host, so a device on the local
  network could spoof a button press and trigger automations (e.g. a gate). Only
  datagrams coming from the PLC's IP are processed; others are dropped and
  logged once per sender. Spoofed DALI/version replies are ignored as well.

### Fixed
- **Entities follow the PLC Online/Offline state.** Only the connectivity sensor
  used to be notified, so lights, switches, shutters and sensors could keep
  showing "available" while the PLC was down (or stay greyed out after it came
  back).
- **States no longer drift.** A periodic resynchronisation (every 30 s, and
  immediately when the PLC comes back online) re-reads relay outputs and digital
  inputs in a few batched Modbus requests and corrects any difference. A short
  grace period ensures a fresh command or edge is never overwritten by an older
  read. If the PLC is unreachable the resync aborts after a single request.
- **A button could stay "dead" after a lost release edge.** The click decoder is
  now silently unblocked when the line is read as released (no fake event).
- **Shutters: a refused command no longer moves the position on screen.** The
  motor is started before the position tracking begins; if the PLC does not
  accept the command, the position is kept and an error is shown. An unconfirmed
  STOP is also reported, since the motor may still be running.

### Changed
- On/off lights and switches report an error in the UI when the PLC refuses a
  command, instead of failing silently.

## [0.0.8] - 2026-09-21

### Fixed
- **Pressing Stop during a shutter movement jumped the position to 0 % or
  100 %** instead of keeping the position where the shutter actually stopped.
  The position is now snapped to the target only when the travel completes
  naturally.

### Documentation
- README: screenshots, configuration details, and a warning never to run
  Wago2HAddon and a Calaos server at the same time.

## [0.0.7] - 2026-09-09

### Added
- **State restore after a restart** for shutters (last estimated position) and
  DALI/DMX lights (on/off, brightness, RGB colour), via `RestoreEntity`.
- Option "Restore state after restart" (enabled by default). Relays and on/off
  lights are not affected: they re-read their real state from the PLC.

## [0.0.6] - 2026-09-07

### Fixed
- **Air-conditioning registers, pumps, solenoid valves and contactors showed up
  as lights.** The importer now honours the Calaos `io_style` attribute
  (`heater`, `pump`, `boiler`, `outlet`): those outputs become `switch` entities
  (outlet device class for `outlet`, matching icons for the others), while
  genuine lights stay `light`.

### Migration note
- The affected entities changed domain (`light.*` → `switch.*`), so their
  `entity_id` changed and the old `light.*` entities were left orphaned (removed
  automatically since 0.1.0).

## [0.0.5] - 2026-09-04

### Changed
- Maintenance release: version bump only, no functional change.

## [0.0.4] - 2026-08-25

### Fixed
- **DALI lights switching back to "off" 1–2 minutes after being turned on.** The
  periodic `WAGO_DALI_GET` poll returned "off" (unreliable query, impossible for
  DMX addresses ≥ 100). As in Calaos, the DALI state is now read once at startup
  (genuine DALI addresses 1–64 only) and then tracked optimistically.

## [0.0.3] - 2026-08-24

### Fixed
- **Clicks were lost intermittently** (issue #2). The UDP socket was opened with
  `SO_REUSEPORT`; after a reload an old socket could stay bound and "steal" part
  of the input packets. The socket is now exclusive, closed cleanly on unload,
  and the bind is retried at startup.

### Added
- A `wago2haddon_event` bus event on every decoded action, in addition to the
  `event` entity (never de-duplicated: a robust automation trigger).
- Defensive handling of several messages in one datagram.
- Clean cancellation of the click-decoder timers when an entity is removed.

## [0.0.2]

### Added
- Calaos program version read with `WAGO_GET_VERSION`, shown on the device page
  and as a diagnostic sensor.
- Online / Offline connectivity sensor based on a periodic Modbus probe.

## [0.0.1]

### Fixed
- Startup error `No module named 'homeassistant.helpers.device_info'` (shown as
  "Platform wago2haddon.light not found"): `DeviceInfo` is imported from
  `homeassistant.helpers.device_registry`.

## [0.0.0]

### Added
- First release: bridge between Home Assistant and a Wago 750-881 PLC running
  the Calaos Codesys program, over Modbus/TCP (502) and UDP (4646).
- Inputs decoded into single / double / triple click and long press (`event` +
  `binary_sensor`), outputs as `light` or `switch`, shutters as `cover` with a
  timed position, DALI single and RGB lights, temperature / analog sensors.
- Suspension of the PLC's internal program through a periodic heartbeat.
- Import of the Calaos `io.xml` file to create all entities automatically.

[0.1.0]: https://github.com/fredsch/Wago2HAddon/compare/0.0.9...0.1.0
[0.0.9]: https://github.com/fredsch/Wago2HAddon/releases/tag/0.0.9
[0.0.8]: https://github.com/fredsch/Wago2HAddon/releases/tag/0.0.8
[0.0.7]: https://github.com/fredsch/Wago2HAddon/releases/tag/0.0.7
[0.0.6]: https://github.com/fredsch/Wago2HAddon/releases/tag/0.0.6
[0.0.5]: https://github.com/fredsch/Wago2HAddon/releases/tag/0.0.5
[0.0.4]: https://github.com/fredsch/Wago2HAddon/releases/tag/0.0.4
[0.0.3]: https://github.com/fredsch/Wago2HAddon/releases/tag/0.0.3
