"""Pure helpers (no Home Assistant import), so they can be unit-tested alone."""
from __future__ import annotations

from .const import (
    COVER_REVERSE_DELAY,
    OUTPUT_READBACK_OFFSET,
    WAGO_841_START_ADDRESS,
    WAGO_KNX_START_ADDRESS,
)


def output_address(var: int, wago_841: bool, knx: bool = False) -> int:
    """Return the Modbus coil address used to WRITE an output (as calaos_base).

    KNX outputs (750-849) are shifted by WAGO_KNX_START_ADDRESS and never get
    the 841 offset; other outputs get WAGO_841_START_ADDRESS when ``wago_841``.
    """
    if knx:
        return var + WAGO_KNX_START_ADDRESS
    return var + (WAGO_841_START_ADDRESS if wago_841 else 0)


def readback_base(var: int, knx: bool = False) -> int:
    """Return the base address an output is READ BACK from (as calaos_base).

    It includes the KNX offset but never the 841 offset; the 0x200 read-back
    offset is added on top of it by :func:`readback_addresses` and by the
    batched resync.
    """
    return var + (WAGO_KNX_START_ADDRESS if knx else 0)


def readback_addresses(base: int) -> tuple[int, int]:
    """Return the coil addresses tried, in order, to read an output back.

    ``base + 0x200`` (WagoExternProc's read_output_bits), raw ``base`` as a
    fallback.
    """
    return base + OUTPUT_READBACK_OFFSET, base


def reverse_wait(
    last_direction: str | None, last_stop: float, direction: str, now: float
) -> float:
    """Return how long to wait before starting a shutter motor in ``direction``.

    Reversing a shutter motor without a pause stresses it (and its relay
    contacts), so after a movement in the opposite direction both coils stay
    off for at least ``COVER_REVERSE_DELAY`` seconds.
    """
    if last_direction is None or last_direction == direction:
        return 0.0
    return max(0.0, COVER_REVERSE_DELAY - (now - last_stop))
