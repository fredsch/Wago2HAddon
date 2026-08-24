"""Base entity for Wago2HAddon."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .hub import WagoHub
from .models import WagoIO


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
