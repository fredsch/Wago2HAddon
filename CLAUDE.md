# CLAUDE.md

Guidance for AI assistants (and humans) working in this repository.

## What this project is

A **Home Assistant custom integration** (installed via HACS) that bridges a
**Wago 750-881 PLC running the Calaos Codesys firmware** to Home Assistant. It
re-implements Calaos' native Wago protocol so the PLC's inputs/outputs appear as
native HA entities, without MQTT or a Docker add-on.

It is a *custom integration*, not a Supervisor *add-on* — that is the correct HACS
vehicle for a persistent heartbeat + native entities. Keep the "Wago2HAddon" name.

## Repository layout

```
custom_components/wago2haddon/
  __init__.py          setup/teardown, builds the hub, imports XML, forwards platforms
  manifest.json        domain, version, codeowners (list, "@user"), iot_class local_push
  const.py             all constants, config keys, defaults, address offsets, UDP strings
  models.py            dataclasses for parsed IO (DigitalInput/Output, ShutterOutput, Dali*, AnalogInput)
  modbus_tcp.py        self-contained async Modbus/TCP client (FC1/FC5/FC3 only)
  hub.py               WagoHub: Modbus + UDP endpoint + heartbeat + monitor + input dispatch + DALI/version queues
  input_decoder.py     raw-edge -> single/double/triple/long decoder (state machine)
  calaos_import.py     parse Calaos io.xml -> list of models
  entity.py            WagoEntity base (unique_id, DeviceInfo with sw_version)
  light.py             WagoDigitalLight (on/off), WagoDaliLight (dimmer), WagoDaliRGBLight (rgb)
  switch.py            WagoSwitch (relay/pump/heater/valve/outlet)
  cover.py             WagoShutter (timed position engine)
  sensor.py            WagoAnalogSensor (temp/analog, polled) + WagoVersionSensor (diagnostic)
  binary_sensor.py     WagoInputBinarySensor (raw line) + WagoConnectivitySensor (online/offline)
  event.py             WagoInputEvent (fires click events + a wago2haddon_event bus event)
  translations/        en.json, fr.json (+ strings.json)
README.md  CHANGELOG.md  hacs.json  LICENSE (GPLv3)
```

## How it works — protocol (authoritative; must match calaos_base)

Two channels to the PLC. These constants and offsets are reverse-engineered from
the Calaos Codesys firmware and from `calaos/calaos_base`
(`src/bin/calaos_server/IO/Wago`, `src/lib/Utils.h`). **Do not change them without
re-checking those sources.**

**Modbus/TCP — port 502, slave id 1**

| Operation | Function code | Address |
|-----------|---------------|---------|
| Read digital input | FC1 read coils | `var` |
| Write digital output | FC5 force coil | `var + 4096` (WAGO_841_START_ADDRESS, when `wago_841`) |
| Read back digital output | FC1 read coils | `var + 512` (0x200), fallback `var` |
| Read analog / temperature | FC3 read holding reg | `var`; temperature = signed16 / 10.0 |

**UDP — port 4646 (WAGO_LISTEN_PORT)**

- Heartbeat every 10 s: send `WAGO_SET_SERVER_IP <local_ip>` then `WAGO_HEARTBEAT`.
  While heartbeats arrive, the firmware sets `HEARTBEAT = TRUE` and **does not run**
  its internal `ManageOutput` block — i.e. the PLC's standalone logic is suspended
  and HA is the sole driver of the outputs. Standalone fallback after 30 s of
  silence.
- Inputs are **pushed** by the PLC: `WAGO INT <var> <0|1>` (raw rising/falling
  edges). Click/double/triple/long is decoded on the HA side (`input_decoder.py`),
  not in the PLC.
- DALI set: `WAGO_DALI_SET <line> <group> <address> <dimm%> <fade>`.
- DALI read: `WAGO_DALI_GET <line> <address>` -> async reply
  `WAGO_DALI_GET <0|1> <dimm%>`.
- Program version: `WAGO_GET_VERSION` -> `WAGO_GET_VERSION <H>.<L> 750-841`
  (the model string is hard-coded in the firmware; parse only the `<H>.<L>` part).

## Key invariants — do not regress these

- **Only Home Assistant drives the outputs** (the PLC internal program is suspended
  by the heartbeat). This makes optimistic state *exact*, and is why DALI/DMX and
  cover state restore is safe.
- **Self-contained Modbus client** (`modbus_tcp.py`). Do NOT add a `pymodbus`
  dependency — it clashes with the copy HA ships. Only FC1/FC5/FC3 are needed.
- **UDP listener socket must be exclusive.** Never bind with `reuse_port=True`: on
  Linux `SO_REUSEPORT` load-balances datagrams across sockets, so a lingering
  socket after a reload silently steals input packets. Bind once; retry on
  address-in-use; wait for the socket to fully close on unload before rebinding.
- **DALI state is NOT polled.** Read once at startup, and only for genuine DALI
  addresses (`address < 100`; DMX >= 100 has no read-back). Track optimistically
  afterwards. (A periodic `WAGO_DALI_GET` poll wrongly reports "off" — that was bug
  1.0.4.)
- **Cover position** is estimated by timing (`time_up` / `time_down`, per
  direction), updated every `_TICK` (0.2 s) during travel. Snap to the exact target
  **only when the travel completes naturally** — never in the cancellation path
  (Stop), or Stop jumps the position to 0/100 (bug 1.0.8).
- **`io_style`** (not `gui_type`) decides light vs switch for `WODigital`:
  `heater`/`pump`/`boiler`/`outlet` -> `switch` (outlet gets device_class OUTLET);
  otherwise a genuine light -> `light`.
- **RestoreEntity** covers shutters + DALI/DMX lights, gated by the `restore_state`
  option (default on). On/off relays and lights instead re-read real Modbus state at
  startup and must keep doing so.
- Input entities fire both an `event` entity update **and** a `wago2haddon_event`
  bus event; keep both (the bus event is the de-dup-proof automation path).

## Entity mapping

`WIDigitalBP/Triple/Long` -> `event` + `binary_sensor`;
`WODigital` -> `light` or `switch` (by `io_style`);
`WOVolet`/`WOVoletSmart` -> `cover`;
`WODali` -> `light` (brightness); `WODaliRVB` -> `light` (rgb);
`WITemp`/`WIAnalog` -> `sensor`. Plus per-PLC diagnostics: connectivity
`binary_sensor` and Calaos-version `sensor`.

## Editing conventions

- Target modern Home Assistant (2024.4+; the config flow already uses
  `ConfigFlowResult`). Python 3.12+, `from __future__ import annotations`.
- Keep the address translation centralized in `hub.py`
  (`read_digital_input`, `set_digital_output`, `read_digital_output`,
  `read_analog`). Entities should not compute Modbus offsets themselves.
- New config options: add to `const.py`, the `_schema()` in `config_flow.py`, the
  `hass.data` store in `__init__.py`, `strings.json`, and both translation files.
- Verify any unfamiliar Home Assistant import path against the HA source before
  using it (see pitfalls) — a wrong module path surfaces as a *misleading*
  "Platform X not found" error.

## Testing / validation (Home Assistant is NOT installed in the dev sandbox)

You cannot `import homeassistant.*` directly. Use these instead:

1. **Byte-compile everything:** `python3 -m py_compile custom_components/wago2haddon/*.py`.
2. **Stub-import test:** create stub `homeassistant.*` / `voluptuous` modules in
   `sys.modules`, then `importlib.import_module` every package module. This catches
   wrong import paths and NameErrors that `py_compile` misses. **Caveat:** stubs must
   use the *real* module paths — a stub named after a wrong path will hide the very
   bug you are looking for (this is exactly how the `device_info` bug slipped
   through once). When in doubt, confirm the symbol's real location in the HA source
   on GitHub.
3. **Offline logic tests:** the HA-free modules (`const`, `models`, `modbus_tcp`,
   `input_decoder`, `calaos_import`) can be copied into a throwaway package and
   tested directly — e.g. parse a real `io.xml`, check Modbus frame bytes, exercise
   the input decoder, and simulate the cover motor/Stop.

## Common pitfalls (already hit — do not repeat)

- `DeviceInfo` is imported from **`homeassistant.helpers.device_registry`**, not
  `homeassistant.helpers.device_info` (which does not exist).
- `EntityCategory` is imported from **`homeassistant.const`** (canonical).
- Never `reuse_port` the UDP socket (see invariants).
- Never poll DALI state periodically.
- `manifest.json` `codeowners` must be a **list** of `@`-prefixed usernames, e.g.
  `["@fredsch"]` — a bare string fails hassfest validation.

## Release process

- Bump `custom_components/wago2haddon/manifest.json` `"version"`.
- Add a `CHANGELOG.md` entry (English) and the `[x.y.z]` link at the bottom.
- Push, then create a GitHub **release tagged exactly `x.y.z`** (no `v` prefix, must
  equal the manifest version). HACS uses tags to offer updates.

## Source-of-truth references

- Calaos Codesys firmware (Structured Text): the PLC side (heartbeat, input send,
  output management, DALI, volet, version).
- `github.com/calaos/calaos_base`, `src/bin/calaos_server/IO/Wago/*` and
  `src/lib/Utils.h`: the C++ client side and the address constants
  (`WAGO_841_START_ADDRESS = 4096`, `WAGO_LISTEN_PORT = 4646`).
