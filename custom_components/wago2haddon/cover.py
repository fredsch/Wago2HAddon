"""Cover platform: roller shutters with timed position estimation.

The Wago is kept in server mode (its internal shutter logic is suspended), so
the two motor coils (up / down) are driven directly and the position is
estimated from the configured full-travel times (time_up / time_down).
"""
from __future__ import annotations

import asyncio
import logging
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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import WagoEntity
from .hub import WagoHub
from .models import ShutterOutput

_LOGGER = logging.getLogger(__name__)

_TICK = 0.2  # seconds between position updates while moving


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    restore: bool = store["restore_state"]
    entities = [
        WagoShutter(hub, io, restore)
        for io in store["devices"]
        if isinstance(io, ShutterOutput)
    ]
    async_add_entities(entities)


class WagoShutter(WagoEntity, CoverEntity, RestoreEntity):
    """A shutter driven by two coils with timed position feedback."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hub: WagoHub, io: ShutterOutput, restore: bool = True) -> None:
        super().__init__(hub, io)
        self._io: ShutterOutput = io
        self._restore = restore
        self._position: float | None = None  # 0 = closed, 100 = open
        self._moving: str | None = None      # None | "open" | "close"
        self._task: asyncio.Task | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restore the last estimated position across restarts (only HA can move
        # these shutters, so the restored value is accurate).
        if not self._restore:
            return
        last = await self.async_get_last_state()
        if last is None or last.state in (None, "unknown", "unavailable"):
            return
        pos = last.attributes.get("current_position")
        if pos is not None:
            try:
                self._position = float(pos)
            except (TypeError, ValueError):
                pass
        elif last.state == "closed":
            self._position = 0.0
        elif last.state == "open":
            self._position = 100.0

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
    async def _set_up(self, on: bool) -> bool:
        return await self._hub.set_digital_output(
            self._io.var_up, self._io.wago_841, on
        )

    async def _set_down(self, on: bool) -> bool:
        return await self._hub.set_digital_output(
            self._io.var_down, self._io.wago_841, on
        )

    async def _all_off(self) -> bool:
        # always try both coils, even if the first write fails
        up_ok = await self._set_up(False)
        down_ok = await self._set_down(False)
        return up_ok and down_ok

    # -- commands -------------------------------------------------------------
    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._go_to(100.0)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._go_to(0.0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._go_to(float(kwargs[ATTR_POSITION]))

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._cancel_task()
        stopped = await self._all_off()
        self._moving = None
        self.async_write_ha_state()
        if not stopped:
            raise HomeAssistantError(
                f"{self.name}: STOP not confirmed by the Wago PLC "
                f"{self._hub.host} - the motor may still be running"
            )

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
        """Start the motor, then track the position in a background task.

        The motor is started HERE, before any timing begins: if the PLC does
        not accept the command, the position is left untouched (the shutter
        has not moved) and the error is shown to the user, instead of a
        position that keeps "moving" on screen while nothing happens.
        """
        await self._cancel_task()
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

        started = await self._all_off()
        if started:
            started = await (
                self._set_up(True) if direction == "open" else self._set_down(True)
            )
        if not started:
            await self._all_off()  # best effort: never leave a coil energised
            self._moving = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"{self.name}: the Wago PLC {self._hub.host} did not accept the "
                "command (unreachable?) - the shutter was not moved"
            )

        self._moving = direction
        self.async_write_ha_state()
        self._task = self.hass.async_create_task(
            self._track(target, start_pos, direction, full)
        )

    async def _track(
        self, target: float, start_pos: float, direction: str, full: float
    ) -> None:
        """Estimate the position from elapsed time while the motor runs."""
        reached_end = False
        try:
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
                if reached and not full_travel:
                    reached_end = True
                    break
                # add a safety margin so end-stops are physically reached
                if full_travel and elapsed >= full + 1.0:
                    reached_end = True
                    break
        finally:
            if not await self._all_off():
                _LOGGER.error(
                    "%s: could not switch the motor off on the Wago PLC %s",
                    self.name, self._hub.host,
                )
            self._moving = None
            # Only snap to the commanded target when the travel actually
            # completed. On a STOP the task is cancelled and this block still
            # runs, so we must keep the real intermediate position instead of
            # jumping to 0/100.
            if reached_end:
                self._position = target
            self.async_write_ha_state()
