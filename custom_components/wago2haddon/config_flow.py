"""Config flow for Wago2HAddon."""
from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

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
)

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any], include_host: bool = True) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if include_host:
        fields[vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, ""))] = str
    fields.update(
        {
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
                CONF_MULTI_CLICK_MS,
                default=defaults.get(CONF_MULTI_CLICK_MS, DEFAULT_MULTI_CLICK_MS),
            ): int,
            vol.Optional(
                CONF_LONG_PRESS_MS,
                default=defaults.get(CONF_LONG_PRESS_MS, DEFAULT_LONG_PRESS_MS),
            ): int,
            vol.Optional(
                CONF_RESTORE_STATE,
                default=defaults.get(CONF_RESTORE_STATE, DEFAULT_RESTORE_STATE),
            ): bool,
        }
    )
    return vol.Schema(fields)


async def _validate_xml(hass: HomeAssistant, user_input: dict[str, Any]) -> dict:
    """Return form errors for the io.xml path (file check off the event loop)."""
    xml_path = (user_input.get(CONF_XML_PATH) or "").strip()
    if xml_path and not await hass.async_add_executor_job(os.path.isfile, xml_path):
        return {CONF_XML_PATH: "xml_not_found"}
    return {}


async def async_migrate_host(
    hass: HomeAssistant, entry: ConfigEntry, old_host: str, new_host: str
) -> None:
    """Re-key the registry entries of ``entry`` from ``old_host`` to ``new_host``.

    Entity unique_ids are ``<host>_<calaos id>`` and the device identifier is
    the host, so changing the PLC address must migrate them; otherwise every
    entity would be recreated (new entity_ids) and the old ones orphaned.
    Entity ids, names, areas and customisations are kept.
    """
    old_prefix = f"{old_host}_"

    @callback
    def _migrate(reg_entry: er.RegistryEntry) -> dict[str, Any] | None:
        if reg_entry.unique_id.startswith(old_prefix):
            return {"unique_id": f"{new_host}_{reg_entry.unique_id[len(old_prefix):]}"}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, old_host)})
    if device is not None:
        dev_reg.async_update_device(
            device.id,
            new_identifiers={(DOMAIN, new_host)},
            configuration_url=f"http://{new_host}",
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
            errors = await _validate_xml(self.hass, user_input)
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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the PLC address while keeping all entities and their ids."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        old_host = entry.data[CONF_HOST]

        if user_input is not None:
            new_host = user_input[CONF_HOST].strip()
            if new_host == old_host:
                return self.async_abort(reason="reconfigure_successful")
            for other in self._async_current_entries(include_ignore=False):
                if other.entry_id != entry.entry_id and other.unique_id == new_host:
                    return self.async_abort(reason="already_configured")

            # Re-key the registries while the entry is unloaded, then reload.
            await self.hass.config_entries.async_unload(entry.entry_id)
            try:
                await async_migrate_host(self.hass, entry, old_host, new_host)
            except ValueError as err:
                # a unique_id with the new address already exists (left over
                # from an old setup): roll back to the previous address
                _LOGGER.error("Could not migrate to %s: %s", new_host, err)
                await async_migrate_host(self.hass, entry, new_host, old_host)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="migration_failed")
            title = entry.title
            if title == f"Wago {old_host}":
                title = f"Wago {new_host}"
            self.hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_HOST: new_host},
                unique_id=new_host,
                title=title,
            )
            _LOGGER.info("PLC address changed from %s to %s", old_host, new_host)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=old_host): str}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return WagoOptionsFlow(entry)


class WagoOptionsFlow(OptionsFlow):
    """Allow editing the settings after setup.

    The PLC address is not an option: it keys the entity unique_ids, so it is
    changed through "Reconfigure", which migrates the registries.
    """

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate_xml(self.hass, user_input)
            if not errors:
                clean = {k: v for k, v in user_input.items() if v != ""}
                return self.async_create_entry(title="", data=clean)

        merged = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(merged, include_host=False),
            errors=errors,
        )
