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
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .calaos_import import parse_calaos_xml
from .const import (
    CONF_HEARTBEAT_INTERVAL,
    CONF_HOST,
    CONF_LOCAL_IP,
    CONF_LONG_PRESS_MS,
    CONF_MODBUS_PORT,
    CONF_MULTI_CLICK_MS,
    CONF_SCAN_INTERVAL,
    CONF_UDP_PORT,
    CONF_XML_PATH,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_LONG_PRESS_MS,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MULTI_CLICK_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UDP_PORT,
    DOMAIN,
)
from .hub import WagoHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.COVER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wago2HAddon from a config entry."""
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
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Could not start Wago hub: {err}") from err

    devices = []
    xml_path = data.get(CONF_XML_PATH)
    if xml_path:
        try:
            devices = await hass.async_add_executor_job(
                parse_calaos_xml, xml_path, host
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to parse Calaos XML %s: %s", xml_path, err)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "devices": devices,
        "scan_interval": data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        "multi_click_ms": data.get(CONF_MULTI_CLICK_MS, DEFAULT_MULTI_CLICK_MS),
        "long_press_ms": data.get(CONF_LONG_PRESS_MS, DEFAULT_LONG_PRESS_MS),
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
