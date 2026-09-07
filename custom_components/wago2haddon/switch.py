"""Switch platform: relays, pumps and other on/off outputs."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import WagoEntity
from .hub import WagoHub
from .models import DigitalOutput

# Optional icon per Calaos io_style, to make the purpose obvious in the UI.
_STYLE_ICONS = {
    "heater": "mdi:radiator",
    "pump": "mdi:pump",
    "boiler": "mdi:water-boiler",
    "valve": "mdi:pipe-valve",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    entities = [
        WagoSwitch(hub, io)
        for io in store["devices"]
        if isinstance(io, DigitalOutput) and not io.as_light
    ]
    async_add_entities(entities)


class WagoSwitch(WagoEntity, SwitchEntity):
    """A relay / pump / heater / valve on-off output."""

    def __init__(self, hub: WagoHub, io: DigitalOutput) -> None:
        super().__init__(hub, io)
        self._io: DigitalOutput = io
        self._attr_is_on = False
        if io.style == "outlet":
            self._attr_device_class = SwitchDeviceClass.OUTLET
        else:
            self._attr_device_class = SwitchDeviceClass.SWITCH
            if io.style in _STYLE_ICONS:
                self._attr_icon = _STYLE_ICONS[io.style]

    async def async_added_to_hass(self) -> None:
        state = await self._hub.read_digital_output(self._io.var)
        if state is not None:
            self._attr_is_on = state
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        if await self._hub.set_digital_output(self._io.var, self._io.wago_841, True):
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self._hub.set_digital_output(self._io.var, self._io.wago_841, False):
            self._attr_is_on = False
            self.async_write_ha_state()

