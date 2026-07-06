"""Central hub for a single Wago PLC: Modbus, UDP, heartbeat and dispatch."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from collections import deque
from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback

from .const import (
    CMD_DALI_GET,
    CMD_DALI_SET,
    CMD_HEARTBEAT,
    CMD_SET_SERVER_IP,
    MSG_INPUT_PREFIX,
    MODBUS_SLAVE_ID,
    OUTPUT_READBACK_OFFSET,
    WAGO_841_START_ADDRESS,
)
from .modbus_tcp import ModbusError, ModbusTcpClient

_LOGGER = logging.getLogger(__name__)


def detect_local_ip(target: str) -> str | None:
    """Return the local IP that would be used to reach ``target``."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target, 9))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_datagram: Callable[[str, str], None]) -> None:
        self._on_datagram = on_datagram
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[override]
        text = data.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()
        if text:
            self._on_datagram(text, addr[0])

    def error_received(self, exc) -> None:  # type: ignore[override]
        _LOGGER.debug("UDP error: %s", exc)


class WagoHub:
    """Owns all communication with one Wago PLC."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        modbus_port: int,
        udp_port: int,
        heartbeat_interval: float,
        local_ip: str | None,
    ) -> None:
        self.hass = hass
        self.host = host
        self.udp_port = udp_port
        self.heartbeat_interval = heartbeat_interval
        self.local_ip = local_ip or detect_local_ip(host)

        self._modbus = ModbusTcpClient(host, modbus_port, slave=MODBUS_SLAVE_ID)
        self._udp_transport: asyncio.DatagramTransport | None = None
        self._heartbeat_task: asyncio.Task | None = None

        # var -> list of callbacks(state: bool) for input dispatch
        self._input_listeners: dict[int, list[Callable[[bool], None]]] = {}

        # serialized DALI GET support
        self._dali_lock = asyncio.Lock()
        self._dali_pending: deque[asyncio.Future] = deque()

        self.available = False

    # -- lifecycle ------------------------------------------------------------
    async def async_setup(self) -> None:
        """Open sockets, start heartbeat. Never raises on PLC being offline."""
        with contextlib.suppress(ModbusError):
            await self._modbus.connect()
            self.available = True

        loop = self.hass.loop
        # Bind on all interfaces so we receive the PLC's input notifications.
        # reuse_port is not available on every platform; fall back gracefully,
        # and keep the hub usable (Modbus only) if the port cannot be bound.
        for kwargs in ({"reuse_port": True}, {}):
            try:
                self._udp_transport, _ = await loop.create_datagram_endpoint(
                    lambda: _UdpProtocol(self._handle_datagram),
                    local_addr=("0.0.0.0", self.udp_port),
                    **kwargs,
                )
                break
            except (OSError, ValueError, NotImplementedError) as err:
                _LOGGER.debug("UDP bind attempt failed (%s): %s", kwargs, err)
        if self._udp_transport is None:
            _LOGGER.warning(
                "Could not bind UDP port %d; input events and DALI state will be "
                "unavailable, but Modbus control still works.",
                self.udp_port,
            )
        self._heartbeat_task = loop.create_task(self._heartbeat_loop())
        _LOGGER.info(
            "Wago hub %s ready (local_ip=%s, udp=%d)",
            self.host, self.local_ip, self.udp_port,
        )

    async def async_shutdown(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
        if self._udp_transport:
            self._udp_transport.close()
        await self._modbus.close()

    # -- heartbeat ------------------------------------------------------------
    async def _heartbeat_loop(self) -> None:
        """Keep the PLC in server mode so its internal program stays suspended."""
        while True:
            try:
                if self.local_ip:
                    self._udp_send(f"{CMD_SET_SERVER_IP} {self.local_ip}")
                self._udp_send(CMD_HEARTBEAT)
            except Exception as err:  # noqa: BLE001 - never kill the loop
                _LOGGER.debug("heartbeat send failed: %s", err)
            await asyncio.sleep(self.heartbeat_interval)

    # -- UDP ------------------------------------------------------------------
    def _udp_send(self, command: str) -> None:
        if self._udp_transport is None:
            return
        # calaos_base sends the string with a trailing NUL (length + 1)
        self._udp_transport.sendto(command.encode("latin-1") + b"\x00",
                                   (self.host, self.udp_port))

    @callback
    def _handle_datagram(self, text: str, src_ip: str) -> None:
        if text.startswith(MSG_INPUT_PREFIX):
            # "WAGO INT <var> <0|1>"
            parts = text.split()
            if len(parts) >= 4:
                try:
                    var = int(parts[2])
                    state = parts[3] == "1"
                except ValueError:
                    return
                self._dispatch_input(var, state)
        elif text.startswith(CMD_DALI_GET):
            # response "WAGO_DALI_GET <status 0/1> <dimm%>"
            if self._dali_pending:
                fut = self._dali_pending.popleft()
                if not fut.done():
                    fut.set_result(text)

    # -- input dispatch -------------------------------------------------------
    @callback
    def register_input(self, var: int, cb: Callable[[bool], None]) -> Callable[[], None]:
        self._input_listeners.setdefault(var, []).append(cb)

        def _unregister() -> None:
            listeners = self._input_listeners.get(var)
            if listeners and cb in listeners:
                listeners.remove(cb)

        return _unregister

    @callback
    def _dispatch_input(self, var: int, state: bool) -> None:
        for cb in self._input_listeners.get(var, []):
            try:
                cb(state)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("input listener for var %d failed", var)

    # -- Modbus helpers (address translation matches calaos_base) -------------
    async def read_digital_input(self, var: int) -> bool | None:
        try:
            return await self._modbus.read_coil(var)
        except ModbusError as err:
            _LOGGER.debug("read_digital_input(%d) failed: %s", var, err)
            return None

    async def set_digital_output(self, var: int, wago_841: bool, value: bool) -> bool:
        addr = var + (WAGO_841_START_ADDRESS if wago_841 else 0)
        try:
            await self._modbus.write_coil(addr, value)
            self.available = True
            return True
        except ModbusError as err:
            _LOGGER.warning("set_digital_output(%d)=%s failed: %s", var, value, err)
            self.available = False
            return False

    async def read_digital_output(self, var: int) -> bool | None:
        """Read an output coil back (offset 0x200, fall back to raw var)."""
        for addr in (var + OUTPUT_READBACK_OFFSET, var):
            try:
                return await self._modbus.read_coil(addr)
            except ModbusError:
                continue
        return None

    async def read_analog(self, var: int, signed: bool = True) -> int | None:
        try:
            if signed:
                return await self._modbus.read_register_signed(var)
            return (await self._modbus.read_holding_registers(var, 1))[0]
        except ModbusError as err:
            _LOGGER.debug("read_analog(%d) failed: %s", var, err)
            return None

    # -- DALI -----------------------------------------------------------------
    def dali_set(self, line: int, group: int, address: int,
                 dimm_percent: int, fade_time: int) -> None:
        dimm_percent = max(0, min(100, int(dimm_percent)))
        self._udp_send(
            f"{CMD_DALI_SET} {line} {group} {address} {dimm_percent} {fade_time}"
        )

    async def dali_get(self, line: int, address: int,
                       timeout: float = 2.0) -> tuple[bool, int] | None:
        """Query a DALI ballast state. Returns (is_on, dimm_percent) or None."""
        async with self._dali_lock:
            fut: asyncio.Future = self.hass.loop.create_future()
            self._dali_pending.append(fut)
            self._udp_send(f"{CMD_DALI_GET} {line} {address}")
            try:
                text = await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError:
                if fut in self._dali_pending:
                    self._dali_pending.remove(fut)
                return None
            parts = text.split()
            if len(parts) >= 3:
                try:
                    return parts[1] != "0", int(parts[2])
                except ValueError:
                    return None
            return None
