"""Light platform: on/off relays, DALI dimmers and RGB DALI lights."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import WagoEntity
from .hub import WagoHub
from .models import DaliOutput, DaliRGBOutput, DigitalOutput


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    entities: list[LightEntity] = []
    for io in store["devices"]:
        if isinstance(io, DigitalOutput) and io.as_light:
            entities.append(WagoDigitalLight(hub, io))
        elif isinstance(io, DaliOutput):
            entities.append(WagoDaliLight(hub, io))
        elif isinstance(io, DaliRGBOutput):
            entities.append(WagoDaliRGBLight(hub, io))
    async_add_entities(entities)


class WagoDigitalLight(WagoEntity, LightEntity):
    """A simple on/off light driven by a Wago digital output coil."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, hub: WagoHub, io: DigitalOutput) -> None:
        super().__init__(hub, io)
        self._io: DigitalOutput = io
        self._attr_is_on = False

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


class WagoDaliLight(WagoEntity, LightEntity):
    """A mono DALI/DMX dimmable light.

    The PLC's internal program is suspended while the bridge runs, so a DALI
    light can only ever be changed from Home Assistant. Its state is therefore
    tracked optimistically (which is exact here) and is NOT polled: matching
    Calaos, the ballast is read once at startup, and only for real DALI
    addresses (1-64). DMX channels (address >= 100) have no read-back.
    """

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, hub: WagoHub, io: DaliOutput) -> None:
        super().__init__(hub, io)
        self._io: DaliOutput = io
        self._attr_is_on = False
        self._attr_brightness = 0

    async def async_added_to_hass(self) -> None:
        ch = self._io.channel
        # One-time initial read for genuine DALI addresses only (no DMX >= 100).
        if ch.address < 100:
            res = await self._hub.dali_get(ch.line, ch.address)
            if res is not None:
                is_on, percent = res
                self._attr_is_on = is_on
                self._attr_brightness = round(percent * 255 / 100)
                self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        ch = self._io.channel
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        elif not self._attr_brightness:
            self._attr_brightness = 255
        percent = round(self._attr_brightness * 100 / 255)
        self._hub.dali_set(ch.line, ch.group, ch.address, percent, ch.fade_time)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        ch = self._io.channel
        self._hub.dali_set(ch.line, ch.group, ch.address, 0, ch.fade_time)
        self._attr_is_on = False
        self.async_write_ha_state()


class WagoDaliRGBLight(WagoEntity, LightEntity):
    """An RGB DALI/DMX light (three channels)."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}

    def __init__(self, hub: WagoHub, io: DaliRGBOutput) -> None:
        super().__init__(hub, io)
        self._io: DaliRGBOutput = io
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_rgb_color = (255, 255, 255)

    def _send(self, rgb: tuple[int, int, int]) -> None:
        r, g, b = rgb
        for ch, comp in (
            (self._io.red, r),
            (self._io.green, g),
            (self._io.blue, b),
        ):
            self._hub.dali_set(ch.line, ch.group, ch.address,
                               round(comp * 100 / 255), ch.fade_time)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_RGB_COLOR in kwargs:
            self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        r, g, b = self._attr_rgb_color
        scale = (self._attr_brightness or 255) / 255
        self._send((round(r * scale), round(g * scale), round(b * scale)))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._send((0, 0, 0))
        self._attr_is_on = False
        self.async_write_ha_state()
