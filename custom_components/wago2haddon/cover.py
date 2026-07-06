"""Cover platform: roller shutters with timed position estimation.

The Wago is kept in server mode (its internal shutter logic is suspended), so
the two motor coils (up / down) are driven directly and the position is
estimated from the configured full-travel times (time_up / time_down).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import WagoEntity
from .hub import WagoHub
from .models import ShutterOutput

_TICK = 0.2  # seconds between position updates while moving


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    entities = [
        WagoShutter(hub, io)
        for io in store["devices"]
        if isinstance(io, ShutterOutput)
    ]
    async_add_entities(entities)


class WagoShutter(WagoEntity, CoverEntity):
    """A shutter driven by two coils with timed position feedback."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hub: WagoHub, io: ShutterOutput) -> None:
        super().__init__(hub, io)
        self._io: ShutterOutput = io
        self._position: float | None = None  # 0 = closed, 100 = open
        self._moving: str | None = None      # None | "open" | "close"
        self._task: asyncio.Task | None = None

    # -- HA properties --------------------------------------------------------
    @property
    def current_cover_position(self) -> int | None:
        return None if self._position is None else round(self._position)

    @property
    def is_closed(self) -> bool | None:
        return None if self._position is None else self._position <= 1

    @property
    def is_opening(self) -> bool:
        return self._moving == "open"

    @property
    def is_closing(self) -> bool:
        return self._moving == "close"

    # -- coil helpers ---------------------------------------------------------
    async def _set_up(self, on: bool) -> None:
        await self._hub.set_digital_output(self._io.var_up, self._io.wago_841, on)

    async def _set_down(self, on: bool) -> None:
        await self._hub.set_digital_output(self._io.var_down, self._io.wago_841, on)

    async def _all_off(self) -> None:
        await self._set_up(False)
        await self._set_down(False)

    # -- commands -------------------------------------------------------------
    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._go_to(100.0)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._go_to(0.0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._go_to(float(kwargs[ATTR_POSITION]))

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._cancel_task()
        await self._all_off()
        self._moving = None
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        await self._cancel_task()

    # -- movement engine ------------------------------------------------------
    async def _cancel_task(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _go_to(self, target: float) -> None:
        await self._cancel_task()
        self._task = self.hass.async_create_task(self._run(target))

    async def _run(self, target: float) -> None:
        target = max(0.0, min(100.0, target))
        # Unknown position: assume the worst case so a full travel calibrates it.
        start_pos = self._position
        if start_pos is None:
            start_pos = 0.0 if target > 50 else 100.0

        if target > start_pos:
            direction, full = "open", max(self._io.time_up, 0.1)
        elif target < start_pos:
            direction, full = "close", max(self._io.time_down, 0.1)
        else:
            return

        try:
            await self._all_off()
            if direction == "open":
                await self._set_up(True)
            else:
                await self._set_down(True)

            self._moving = direction
            self.async_write_ha_state()

            start_time = time.monotonic()
            full_travel = target in (0.0, 100.0)
            while True:
                await asyncio.sleep(_TICK)
                elapsed = time.monotonic() - start_time
                delta = elapsed / full * 100.0
                pos = start_pos + delta if direction == "open" else start_pos - delta
                self._position = max(0.0, min(100.0, pos))
                self.async_write_ha_state()

                reached = (
                    (direction == "open" and self._position >= target)
                    or (direction == "close" and self._position <= target)
                )
                # add a safety margin so end-stops are physically reached
                if reached and not full_travel:
                    break
                if full_travel and elapsed >= full + 1.0:
                    break
        finally:
            await self._all_off()
            self._moving = None
            if target in (0.0, 100.0):
                self._position = target
            self.async_write_ha_state()
