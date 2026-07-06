"""A tiny self-contained asyncio Modbus/TCP client.

Only the three function codes used by the Calaos Wago driver are implemented:

* FC1  Read Coils            (digital inputs and output read-back)
* FC5  Write Single Coil     (relay / light / shutter outputs)
* FC3  Read Holding Register (analog / temperature inputs)

Implementing this locally (instead of depending on pymodbus) avoids version
clashes with the pymodbus copy that Home Assistant already ships.
"""
from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)


class ModbusError(Exception):
    """Raised on a Modbus protocol or transport error."""


class ModbusTcpClient:
    """Serialized async Modbus/TCP client (one transaction at a time)."""

    def __init__(self, host: str, port: int = 502, slave: int = 1,
                 timeout: float = 3.0) -> None:
        self._host = host
        self._port = port
        self._slave = slave
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise ModbusError(f"connect to {self._host}:{self._port} failed: {err}") from err

    async def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
        self._reader = None
        self._writer = None

    def _next_tid(self) -> int:
        self._tid = (self._tid + 1) & 0xFFFF
        return self._tid

    async def _transaction(self, pdu: bytes) -> bytes:
        """Send a PDU wrapped in an MBAP header and return the response PDU."""
        async with self._lock:
            if not self.connected:
                await self.connect()
            tid = self._next_tid()
            # MBAP: transaction id, protocol id (0), length, unit id
            header = struct.pack(">HHHB", tid, 0, len(pdu) + 1, self._slave)
            assert self._writer is not None and self._reader is not None
            try:
                self._writer.write(header + pdu)
                await self._writer.drain()
                resp_header = await asyncio.wait_for(
                    self._reader.readexactly(7), timeout=self._timeout
                )
                r_tid, _proto, length, _unit = struct.unpack(">HHHB", resp_header)
                body = await asyncio.wait_for(
                    self._reader.readexactly(length - 1), timeout=self._timeout
                )
            except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError) as err:
                await self.close()
                raise ModbusError(f"transaction failed: {err}") from err

            if r_tid != tid:
                await self.close()
                raise ModbusError("transaction id mismatch")

            func = body[0]
            if func & 0x80:  # exception response
                code = body[1] if len(body) > 1 else 0
                raise ModbusError(f"modbus exception, function {func & 0x7F}, code {code}")
            return body

    async def read_coils(self, address: int, count: int = 1) -> list[bool]:
        """FC1 - read `count` coils starting at `address`."""
        pdu = struct.pack(">BHH", 0x01, address & 0xFFFF, count)
        body = await self._transaction(pdu)
        byte_count = body[1]
        data = body[2:2 + byte_count]
        bits: list[bool] = []
        for i in range(count):
            bits.append(bool((data[i // 8] >> (i % 8)) & 0x01))
        return bits

    async def read_coil(self, address: int) -> bool:
        return (await self.read_coils(address, 1))[0]

    async def write_coil(self, address: int, value: bool) -> None:
        """FC5 - force a single coil."""
        pdu = struct.pack(">BHH", 0x05, address & 0xFFFF, 0xFF00 if value else 0x0000)
        await self._transaction(pdu)

    async def read_holding_registers(self, address: int, count: int = 1) -> list[int]:
        """FC3 - read `count` 16-bit holding registers starting at `address`."""
        pdu = struct.pack(">BHH", 0x03, address & 0xFFFF, count)
        body = await self._transaction(pdu)
        byte_count = body[1]
        data = body[2:2 + byte_count]
        return [struct.unpack(">H", data[i:i + 2])[0] for i in range(0, byte_count, 2)]

    async def read_register_signed(self, address: int) -> int:
        raw = (await self.read_holding_registers(address, 1))[0]
        return raw - 0x10000 if raw >= 0x8000 else raw
