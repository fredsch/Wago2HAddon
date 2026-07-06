"""Event platform: click / double-click / triple-click / long-press."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import WagoEntity
from .hub import WagoHub
from .input_decoder import InputDecoder
from .models import DigitalInput


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    hub: WagoHub = store["hub"]
    entities = [
        WagoInputEvent(hub, io, store["multi_click_ms"], store["long_press_ms"])
        for io in store["devices"]
        if isinstance(io, DigitalInput)
    ]
    async_add_entities(entities)


class WagoInputEvent(WagoEntity, EventEntity):
    """Fires button events decoded from raw input edges."""

    def __init__(
        self, hub: WagoHub, io: DigitalInput, multi_click_ms: int, long_press_ms: int
    ) -> None:
        super().__init__(hub, io)
        self._io: DigitalInput = io
        self._unregister: Callable[[], None] | None = None
        self._decoder = InputDecoder(
            io.kind,
            emit=self._emit,
            schedule=self._schedule,
            multi_click_ms=multi_click_ms,
            long_press_ms=long_press_ms,
        )
        self._attr_event_types = self._decoder.event_types()
        self._attr_translation_key = "button"

    def _schedule(self, delay: float, cb: Callable[[], None]) -> Callable[[], None]:
        handle = self.hass.loop.call_later(delay, cb)
        return handle.cancel

    @callback
    def _emit(self, event_type: str) -> None:
        self._trigger_event(event_type)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._unregister = self._hub.register_input(self._io.var, self._decoder.feed)

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister:
            self._unregister()
