"""Config flow for Wago2HAddon."""
from __future__ import annotations

import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_HEARTBEAT_INTERVAL,
    CONF_HOST,
    CONF_LOCAL_IP,
    CONF_LONG_PRESS_MS,
    CONF_MODBUS_PORT,
    CONF_MULTI_CLICK_MS,
    CONF_SCAN_INTERVAL,
    CONF_UDP_PORT,
    CONF_WAGO_841,
    CONF_XML_PATH,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_LONG_PRESS_MS,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MULTI_CLICK_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UDP_PORT,
    DEFAULT_WAGO_841,
    DOMAIN,
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Optional(
                CONF_MODBUS_PORT,
                default=defaults.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT),
            ): int,
            vol.Optional(
                CONF_UDP_PORT, default=defaults.get(CONF_UDP_PORT, DEFAULT_UDP_PORT)
            ): int,
            vol.Optional(
                CONF_XML_PATH, default=defaults.get(CONF_XML_PATH, "")
            ): str,
            vol.Optional(
                CONF_LOCAL_IP, default=defaults.get(CONF_LOCAL_IP, "")
            ): str,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): int,
            vol.Optional(
                CONF_HEARTBEAT_INTERVAL,
                default=defaults.get(
                    CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL
                ),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_WAGO_841, default=defaults.get(CONF_WAGO_841, DEFAULT_WAGO_841)
            ): bool,
            vol.Optional(
                CONF_MULTI_CLICK_MS,
                default=defaults.get(CONF_MULTI_CLICK_MS, DEFAULT_MULTI_CLICK_MS),
            ): int,
            vol.Optional(
                CONF_LONG_PRESS_MS,
                default=defaults.get(CONF_LONG_PRESS_MS, DEFAULT_LONG_PRESS_MS),
            ): int,
        }
    )


class WagoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wago2HAddon."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            xml_path = user_input.get(CONF_XML_PATH, "").strip()
            if xml_path and not os.path.isfile(xml_path):
                errors[CONF_XML_PATH] = "xml_not_found"
            if not errors:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                # strip empty optional strings
                clean = {k: v for k, v in user_input.items() if v != ""}
                clean[CONF_HOST] = host
                return self.async_create_entry(title=f"Wago {host}", data=clean)

        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return WagoOptionsFlow(entry)


class WagoOptionsFlow(OptionsFlow):
    """Allow editing the settings after setup."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            xml_path = user_input.get(CONF_XML_PATH, "").strip()
            if xml_path and not os.path.isfile(xml_path):
                errors[CONF_XML_PATH] = "xml_not_found"
            if not errors:
                clean = {k: v for k, v in user_input.items() if v != ""}
                return self.async_create_entry(title="", data=clean)

        merged = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_schema(merged), errors=errors
        )
