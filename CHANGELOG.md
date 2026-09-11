# Changelog

All notable changes to Wago2HAddon are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and the project follows semantic versioning.

## [1.0.7] - 2026-08-24

### Added
- **State restore after a restart** for **shutters** (last estimated position) and
  **DALI/DMX lights** (on/off, brightness, RGB color), via `RestoreEntity`. No more
  shutter stuck at "unknown" or DMX/RGB light coming back off after a restart or an
  update of Home Assistant. The restore is accurate here since only Home Assistant
  drives these outputs (the PLC's internal program is suspended).
- **Toggle option** "Restore state after restart" in the integration settings
  (Configure), enabled by default. Relays and on/off lights are not affected: they
  keep re-reading their real state from the PLC at startup.

## [1.0.6] - 2026-08-24

### Fixed
- **Air-conditioning registers, pumps, solenoid valves and contactors showed up as
  lights.** In the Calaos file these outputs have `gui_type="light"` but a separate
  `io_style` attribute (`heater`, `pump`, `boiler`, `outlet`) that the importer
  ignored. It now honors it: those outputs are created as **`switch`** entities
  (with the *outlet* device class for `outlet`, and a fitting icon for
  radiator/pump/boiler), while genuine lights stay as `light`.

### Migration note
- After the update, the affected entities change domain (`light.*` → `switch.*`):
  their `entity_id` changes and the old `light.*` entities become orphaned. Update
  your dashboards and automations, and remove the `light.*` entities that became
  unavailable.

## [1.0.5] - 2026-08-24

### Changed
- Maintenance release: version bump only, no functional change since 1.0.4.

## [1.0.4] - 2026-08-24

### Fixed
- **DALI lights switching back to "off" ~1-2 min after being turned on.** The DALI
  state was polled periodically via `WAGO_DALI_GET`, but that read returns "off"
  (the query is unreliable, and impossible for DMX at address >= 100), which
  overwrote the real state. In line with Calaos, DALI state is no longer polled in a
  loop: it is read **once at startup** (and only for genuine DALI addresses 1-64),
  then tracked **optimistically**. Since the PLC's internal program is suspended, a
  DALI light can only be changed from Home Assistant, so the optimistic state is
  exact.

## [1.0.3] - 2026-08-24

### Fixed
- **Unstable inputs: clicks were lost intermittently** (issue #2). The UDP listener
  socket (port 4646) was opened with `SO_REUSEPORT`; on Linux the kernel then
  spreads incoming datagrams across every socket bound to that port. After a reload,
  an update or a restart, an old socket sometimes stayed bound and "stole" a share
  of the `WAGO INT` packets, which were silently lost. The socket is now
  **exclusive**: every input packet reaches the single listening instance.
- Clean close of the UDP socket on unload (waiting for its actual release) and a
  bind retry at startup, so a reload never leaves two sockets competing for the port.

### Added
- A **bus event** `wago2haddon_event` is fired on every decoded action (single /
  double / triple click, long press), in addition to the `event` entity. An `event`
  trigger on this event is fully reliable (never de-duplicated) and is a robust
  alternative for automations.
- Defensive handling of multiple messages per datagram (no message dropped if the
  PLC were to batch them).
- Clean cancellation of the input decoder timers when an entity is removed (avoids
  an event firing after a reload).

## [1.0.2]

### Added
- **Calaos program version** installed on the PLC, read via the UDP
  `WAGO_GET_VERSION` command: shown on the device page ("Firmware version" field)
  and exposed as a diagnostic sensor, refreshed on every reconnection.
- **Online / Offline connectivity sensor** (`binary_sensor`, *connectivity* class),
  based on a reliable Modbus probe run periodically.

## [1.0.1]

### Fixed
- Startup error `ModuleNotFoundError: No module named
  'homeassistant.helpers.device_info'` (which surfaced as the misleading message
  "Platform wago2haddon.light not found"). `DeviceInfo` is now imported from
  `homeassistant.helpers.device_registry`.

## [1.0.0]

### Added
- First release: Home Assistant ↔ Wago 750-881 PLC bridge running the Calaos
  Codesys program, over Modbus/TCP (502) and UDP (4646).
- **Inputs** decoded into single / double / triple click and long press (`event` +
  `binary_sensor` entities).
- **Outputs** as `light` or `switch` (relays, lights, pumps).
- **Shutters** (`WOVoletSmart`) as `cover` with position estimated from the up/down
  travel times in seconds.
- **DALI** single (dimming) and **RGB** (color) via `WAGO_DALI_SET`.
- **Temperature / analog** (PT100/PT1000) as `sensor`, periodic read (2 min by
  default).
- **Internal program suspension** of the PLC while the gateway runs, via a periodic
  heartbeat (server mode).
- **Import** of the Calaos `io.xml` configuration to create all entities
  automatically.

[1.0.7]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.7
[1.0.6]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.6
[1.0.5]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.5
[1.0.4]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.4
[1.0.3]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.3
[1.0.2]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.2
[1.0.1]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.1
[1.0.0]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.0
