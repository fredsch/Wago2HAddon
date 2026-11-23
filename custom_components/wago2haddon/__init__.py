"""The Wago2HAddon integration.

Bridges a Wago 750-881 PLC running the Calaos Codesys program with Home
Assistant, over Modbus/TCP (I/O) and UDP port 4646 (heartbeat, DALI, input
notifications). While the bridge is running, a periodic heartbeat keeps the
PLC in "server mode", which suspends its internal standalone program.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .calaos_import import parse_calaos_xml
from .const import (
    CONF_HEARTBEAT_INTERVAL,
    CONF_HOST,
    CONF_LOCAL_IP,
    CONF_LONG_PRESS_MS,
    CONF_MODBUS_PORT,
    CONF_MULTI_CLICK_MS,
    CONF_RESTORE_STATE,
    CONF_SCAN_INTERVAL,
    CONF_UDP_PORT,
    CONF_XML_PATH,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_LONG_PRESS_MS,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MULTI_CLICK_MS,
    DEFAULT_RESTORE_STATE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UDP_PORT,
    DOMAIN,
    UID_CONNECTIVITY,
    UID_VERSION,
)
from .hub import UdpBindError, WagoHub
from .models import (
    AnalogInput,
    DaliOutput,
    DaliRGBOutput,
    DigitalInput,
    DigitalOutput,
    ShutterOutput,
    WagoIO,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.COVER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
]


def expected_entities(host: str, devices: list[WagoIO]) -> set[tuple[str, str]]:
    """Return the (platform domain, unique_id) pairs the integration creates."""
    expected = {
        (Platform.BINARY_SENSOR, f"{host}_{UID_CONNECTIVITY}"),
        (Platform.SENSOR, f"{host}_{UID_VERSION}"),
    }
    for io in devices:
        uid = f"{host}_{io.io_id}"
        if isinstance(io, DigitalInput):
            expected.add((Platform.BINARY_SENSOR, uid))
            expected.add((Platform.EVENT, uid))
        elif isinstance(io, DigitalOutput):
            expected.add((Platform.LIGHT if io.as_light else Platform.SWITCH, uid))
        elif isinstance(io, ShutterOutput):
            expected.add((Platform.COVER, uid))
        elif isinstance(io, (DaliOutput, DaliRGBOutput)):
            expected.add((Platform.LIGHT, uid))
        elif isinstance(io, AnalogInput):
            expected.add((Platform.SENSOR, uid))
    return expected


@callback
def _async_remove_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, host: str, devices: list[WagoIO]
) -> None:
    """Remove registry entries no longer produced by the current io.xml.

    Covers IO points deleted from io.xml and entities whose platform changed
    (e.g. the light.* -> switch.* move of 0.0.6). Only called after a
    successful, non-empty import, so a missing or broken file never wipes
    the entities.
    """
    expected = expected_entities(host, devices)
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (reg_entry.domain, reg_entry.unique_id) not in expected:
            _LOGGER.info(
                "Removing %s: no longer present in the Calaos io.xml",
                reg_entry.entity_id,
            )
            registry.async_remove(reg_entry.entity_id)


@callback
def _async_move_host_out_of_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate a PLC address set through the old options form into ``data``.

    Up to 0.0.9 the address could be changed in the options; it is now only
    changed via "Reconfigure". Entities were keyed on that option address, so
    it simply becomes the entry's address (and unique_id): nothing changes
    for existing entities.
    """
    if CONF_HOST not in entry.options:
        return
    options = dict(entry.options)
    host = options.pop(CONF_HOST)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_HOST: host},
        options=options,
        unique_id=host,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wago2HAddon from a config entry."""
    _async_move_host_out_of_options(hass, entry)
    data = {**entry.data, **entry.options}
    host = data[CONF_HOST]

    hub = WagoHub(
        hass,
        host=host,
        modbus_port=data.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT),
        udp_port=data.get(CONF_UDP_PORT, DEFAULT_UDP_PORT),
        heartbeat_interval=data.get(CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL),
        local_ip=data.get(CONF_LOCAL_IP) or None,
    )

    try:
        await hub.async_setup()
    except UdpBindError as err:
        # No heartbeat possible: do not start at all rather than letting the
        # PLC's internal program and Home Assistant both drive the outputs.
        # Home Assistant retries automatically.
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Could not start Wago hub: {err}") from err

    devices: list[WagoIO] = []
    xml_path = data.get(CONF_XML_PATH)
    if xml_path:
        try:
            devices = await hass.async_add_executor_job(
                parse_calaos_xml, xml_path, host
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to parse Calaos XML %s: %s", xml_path, err)
        else:
            if devices:
                _async_remove_stale_entities(hass, entry, host, devices)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "devices": devices,
        "scan_interval": data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        "multi_click_ms": data.get(CONF_MULTI_CLICK_MS, DEFAULT_MULTI_CLICK_MS),
        "long_press_ms": data.get(CONF_LONG_PRESS_MS, DEFAULT_LONG_PRESS_MS),
        "restore_state": data.get(CONF_RESTORE_STATE, DEFAULT_RESTORE_STATE),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        store = hass.data[DOMAIN].pop(entry.entry_id)
        await store["hub"].async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
