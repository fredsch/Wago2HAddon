"""Base entity for Wago2HAddon."""
from __future__ import annotations

import time
from typing import Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, RESYNC_GRACE
from .hub import WagoHub
from .models import DigitalOutput, WagoIO


class WagoEntity(Entity):
    """Common base for all Wago entities."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, hub: WagoHub, io: WagoIO) -> None:
        self._hub = hub
        self._io = io
        self._attr_unique_id = f"{hub.host}_{io.io_id}"
        name = io.name
        if io.room:
            name = f"{io.room} - {io.name}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.host)},
            name=f"Wago PLC {hub.host}",
            manufacturer="Wago",
            model="750-881 (Calaos Codesys)",
            sw_version=hub.sw_version,
            configuration_url=f"http://{hub.host}",
        )

    @property
    def available(self) -> bool:
        return self._hub.available

    async def async_added_to_hass(self) -> None:
        """Follow the PLC Online/Offline state.

        Subclasses overriding this method MUST call
        ``await super().async_added_to_hass()``.
        """
        await super().async_added_to_hass()
        self.async_on_remove(
            self._hub.register_availability(self._on_hub_availability)
        )

    @callback
    def _on_hub_availability(self, _available: bool) -> None:
        # Re-publish so HA re-evaluates `available` (greys out / restores).
        self.async_write_ha_state()


class WagoDigitalOutputEntity(WagoEntity):
    """Shared on/off logic for relay outputs (light and switch platforms).

    The real coil state is read at startup and then re-checked on every hub
    resync, so Home Assistant never keeps showing a state the PLC does not
    have (e.g. after the PLC ran its own program during a network outage).
    """

    def __init__(self, hub: WagoHub, io: DigitalOutput) -> None:
        super().__init__(hub, io)
        self._io: DigitalOutput = io
        self._attr_is_on = False
        self._last_command = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self._hub.read_digital_output(self._io.var)
        if state is not None:
            self._attr_is_on = state
            self.async_write_ha_state()
        self.async_on_remove(
            self._hub.register_output_state(self._io.var, self._on_resync)
        )

    @callback
    def _on_resync(self, state: bool) -> None:
        # A resync read may have been taken just before our own command was
        # applied: never let it overwrite a fresh command.
        if time.monotonic() - self._last_command < RESYNC_GRACE:
            return
        if state != self._attr_is_on:
            self._attr_is_on = state
            self.async_write_ha_state()

    async def _async_set(self, value: bool) -> None:
        self._last_command = time.monotonic()
        if not await self._hub.set_digital_output(
            self._io.var, self._io.wago_841, value
        ):
            raise HomeAssistantError(
                f"{self.name}: the Wago PLC {self._hub.host} did not accept "
                "the command (unreachable?)"
            )
        self._attr_is_on = value
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
