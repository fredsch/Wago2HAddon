"""The self-contained Modbus/TCP client against a tiny in-process server."""
import asyncio
import struct

import pytest
from conftest import load

modbus = load("modbus_tcp")


class FakePlc:
    """Answers FC1 / FC3 / FC5 and records every request PDU."""

    def __init__(self):
        self.coils = {0: True, 2: True}
        self.registers = {10: 0xFF38}  # -200 signed -> -20.0 degC
        self.requests = []

    async def handle(self, reader, writer):
        try:
            while True:
                header = await reader.readexactly(7)
                tid, _proto, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                self.requests.append((unit, pdu))
                func = pdu[0]
                addr, value = struct.unpack(">HH", pdu[1:5])
                if func == 0x01:
                    bits = 0
                    for i in range(value):
                        if self.coils.get(addr + i):
                            bits |= 1 << i
                    nbytes = (value + 7) // 8
                    body = bytes([func, nbytes]) + bits.to_bytes(nbytes, "little")
                elif func == 0x03:
                    regs = b"".join(
                        struct.pack(">H", self.registers.get(addr + i, 0))
                        for i in range(value)
                    )
                    body = bytes([func, len(regs)]) + regs
                elif func == 0x05:
                    self.coils[addr] = value == 0xFF00
                    body = pdu
                else:
                    body = bytes([func | 0x80, 0x01])
                writer.write(struct.pack(">HHHB", tid, 0, len(body) + 1, unit) + body)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()


def run(coro):
    return asyncio.run(coro)


async def _with_server(test):
    plc = FakePlc()
    server = await asyncio.start_server(plc.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = modbus.ModbusTcpClient("127.0.0.1", port, slave=1, timeout=2)
    try:
        await test(client, plc)
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


def test_read_coils():
    async def test(client, plc):
        assert await client.read_coils(0, 3) == [True, False, True]
        assert await client.read_coil(1) is False
        assert plc.requests[0] == (1, struct.pack(">BHH", 0x01, 0, 3))

    run(_with_server(test))


def test_write_coil_frame():
    async def test(client, plc):
        await client.write_coil(4096 + 5, True)
        assert plc.requests[-1][1] == struct.pack(">BHH", 0x05, 4101, 0xFF00)
        assert plc.coils[4101] is True
        await client.write_coil(4101, False)
        assert plc.requests[-1][1] == struct.pack(">BHH", 0x05, 4101, 0x0000)

    run(_with_server(test))


def test_read_register_signed():
    async def test(client, plc):
        assert await client.read_register_signed(10) == -200
        assert await client.read_holding_registers(10, 1) == [0xFF38]

    run(_with_server(test))


def test_exception_response_raises():
    async def test(client, plc):
        with pytest.raises(modbus.ModbusError):
            await client._transaction(struct.pack(">BHH", 0x2B, 0, 0))

    run(_with_server(test))


def test_connect_failure_raises():
    async def test():
        client = modbus.ModbusTcpClient("127.0.0.1", 1, timeout=0.5)
        with pytest.raises(modbus.ModbusError):
            await client.read_coil(0)

    run(test())
