"""Binary sensor platform: raw state of each digital input line."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import WagoEntity
from .hub import WagoHub
from .models import DigitalInput


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    entities = [
        WagoInputBinarySensor(hub, io)
        for io in store["devices"]
        if isinstance(io, DigitalInput)
    ]
    async_add_entities(entities)


class WagoInputBinarySensor(WagoEntity, BinarySensorEntity):
    """Reflects the raw open/closed state of a digital input."""

    def __init__(self, hub: WagoHub, io: DigitalInput) -> None:
        super().__init__(hub, io)
        self._io: DigitalInput = io
        self._attr_is_on = False
        self._unregister = None

    async def async_added_to_hass(self) -> None:
        # initial read via Modbus (push updates arrive over UDP afterwards)
        state = await self._hub.read_digital_input(self._io.var)
        if state is not None:
            self._attr_is_on = state
            self.async_write_ha_state()
        self._unregister = self._hub.register_input(self._io.var, self._on_edge)

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister:
            self._unregister()

    @callback
    def _on_edge(self, state: bool) -> None:
        self._attr_is_on = state
        self.async_write_ha_state()
