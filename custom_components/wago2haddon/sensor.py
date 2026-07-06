"""Sensor platform: temperature (PT100/PT1000) and generic analog inputs."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .entity import WagoEntity
from .hub import WagoHub
from .models import AnalogInput


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    scan = timedelta(seconds=store["scan_interval"])
    entities = [
        WagoAnalogSensor(hub, io, scan)
        for io in store["devices"]
        if isinstance(io, AnalogInput)
    ]
    async_add_entities(entities)


class WagoAnalogSensor(WagoEntity, SensorEntity):
    """A temperature or analog value read from a Wago register.

    Polled on a slow interval (default 2 minutes) as the user requested; the
    value does not need to be real-time.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub: WagoHub, io: AnalogInput, scan: timedelta) -> None:
        super().__init__(hub, io)
        self._io: AnalogInput = io
        self._scan = scan
        if io.is_temp:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif io.unit:
            self._attr_native_unit_of_measurement = io.unit

    async def async_added_to_hass(self) -> None:
        await self._refresh()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._refresh_cb, self._scan)
        )

    @callback
    def _refresh_cb(self, _now) -> None:
        self.hass.async_create_task(self._refresh())

    async def _refresh(self) -> None:
        raw = await self._hub.read_analog(self._io.var, signed=True)
        if raw is None:
            return
        if self._io.is_temp:
            # Wago RTD modules (750-460/750-640) return tenths of a degree.
            value = raw / 10.0
        else:
            value = float(raw)
        value = self._io.coeff_a * value + self._io.coeff_b + self._io.offset
        self._attr_native_value = round(value, 2)
        self.async_write_ha_state()
