"""Binary sensor platform: raw state of each digital input line."""
from __future__ import annotations

import time

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, RESYNC_GRACE
from .entity import WagoEntity
from .hub import WagoHub
from .models import DigitalInput, WagoIO


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    entities: list[BinarySensorEntity] = [WagoConnectivitySensor(hub)]
    entities += [
        WagoInputBinarySensor(hub, io)
        for io in store["devices"]
        if isinstance(io, DigitalInput)
    ]
    async_add_entities(entities)


class WagoConnectivitySensor(WagoEntity, BinarySensorEntity):
    """Reflects whether the PLC is reachable (Online/Offline).

    State updates come from the base class availability subscription.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: WagoHub) -> None:
        io = WagoIO(io_id="connectivity", name="connectivité",
                    io_type="connectivity", host=hub.host)
        super().__init__(hub, io)
        self._attr_name = f"Wago {hub.host} connectivité"

    @property
    def available(self) -> bool:
        # must stay available to be able to report "off" (offline)
        return True

    @property
    def is_on(self) -> bool:
        return self._hub.available


class WagoInputBinarySensor(WagoEntity, BinarySensorEntity):
    """Reflects the raw open/closed state of a digital input.

    Real-time updates arrive as UDP edges; the periodic hub resync corrects
    the state if an edge was ever lost.
    """

    def __init__(self, hub: WagoHub, io: DigitalInput) -> None:
        super().__init__(hub, io)
        self._io: DigitalInput = io
        self._attr_is_on = False
        self._last_edge = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # initial read via Modbus (push updates arrive over UDP afterwards)
        state = await self._hub.read_digital_input(self._io.var)
        if state is not None:
            self._attr_is_on = state
            self.async_write_ha_state()
        self.async_on_remove(self._hub.register_input(self._io.var, self._on_edge))
        self.async_on_remove(
            self._hub.register_input_state(self._io.var, self._on_resync)
        )

    @callback
    def _on_edge(self, state: bool) -> None:
        self._last_edge = time.monotonic()
        self._attr_is_on = state
        self.async_write_ha_state()

    @callback
    def _on_resync(self, state: bool) -> None:
        # never let a resync read overwrite an edge that just arrived
        if time.monotonic() - self._last_edge < RESYNC_GRACE:
            return
        if state != self._attr_is_on:
            self._attr_is_on = state
            self.async_write_ha_state()
