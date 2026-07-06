"""Import a Calaos ``io.xml`` configuration file into Wago IO models."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from .const import (
    T_INPUT_ANALOG,
    T_INPUT_BP,
    T_INPUT_LONG,
    T_INPUT_TEMP,
    T_INPUT_TRIPLE,
    T_OUTPUT_DALI,
    T_OUTPUT_DALI_RGB,
    T_OUTPUT_DIGITAL,
    T_OUTPUT_VOLET,
    T_OUTPUT_VOLET_SMART,
)
from .models import (
    AnalogInput,
    DaliChannel,
    DaliOutput,
    DaliRGBOutput,
    DigitalInput,
    DigitalOutput,
    ShutterOutput,
    WagoIO,
)

_LOGGER = logging.getLogger(__name__)
_NS = "{http://www.calaos.fr}"


def _to_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_true(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


def _channel(a: dict, prefix: str) -> DaliChannel:
    return DaliChannel(
        line=_to_int(a.get(f"{prefix}line"), 1),
        address=_to_int(a.get(f"{prefix}address"), 1),
        group=_to_int(a.get(f"{prefix}group"), 0),
        fade_time=_to_int(a.get(f"{prefix}fade_time"), 1),
    )


def parse_calaos_xml(path: str, only_host: str | None = None) -> list[WagoIO]:
    """Parse ``path`` and return the list of Wago IO points it contains.

    ``only_host`` optionally restricts the result to a single PLC IP.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    devices: list[WagoIO] = []

    for room in root.iter(f"{_NS}room"):
        room_name = room.get("name", "")
        for el in room:
            a = el.attrib
            io_type = a.get("type")
            host = a.get("host", "")
            if io_type is None or host == "":
                continue
            if only_host is not None and host != only_host:
                continue
            if not _is_true(a.get("enabled"), True):
                continue

            io_id = a.get("id", "")
            name = a.get("name", io_id)
            common = dict(io_id=io_id, name=name, io_type=io_type,
                          host=host, room=room_name, extra=dict(a))

            dev: WagoIO | None = None

            if io_type in (T_INPUT_BP, T_INPUT_TRIPLE, T_INPUT_LONG):
                kind = {
                    T_INPUT_BP: "bp",
                    T_INPUT_TRIPLE: "triple",
                    T_INPUT_LONG: "long",
                }[io_type]
                dev = DigitalInput(
                    var=_to_int(a.get("var")),
                    kind=kind,
                    knx=_is_true(a.get("knx")),
                    **common,
                )

            elif io_type == T_OUTPUT_DIGITAL:
                gtype = (a.get("gtype") or a.get("gui_type") or "light").lower()
                dev = DigitalOutput(
                    var=_to_int(a.get("var")),
                    wago_841=_is_true(a.get("wago_841"), True),
                    knx=_is_true(a.get("knx")),
                    as_light=(gtype == "light"),
                    **common,
                )

            elif io_type in (T_OUTPUT_VOLET, T_OUTPUT_VOLET_SMART):
                dev = ShutterOutput(
                    var_up=_to_int(a.get("var_up")),
                    var_down=_to_int(a.get("var_down")),
                    time_up=_to_float(a.get("time_up"), 30.0),
                    time_down=_to_float(a.get("time_down"), 30.0),
                    wago_841=_is_true(a.get("wago_841"), True),
                    **common,
                )

            elif io_type == T_OUTPUT_DALI:
                dev = DaliOutput(channel=_channel(a, ""), **common)

            elif io_type == T_OUTPUT_DALI_RGB:
                dev = DaliRGBOutput(
                    red=_channel(a, "r"),
                    green=_channel(a, "g"),
                    blue=_channel(a, "b"),
                    **common,
                )

            elif io_type in (T_INPUT_TEMP, T_INPUT_ANALOG):
                dev = AnalogInput(
                    var=_to_int(a.get("var")),
                    is_temp=(io_type == T_INPUT_TEMP),
                    coeff_a=_to_float(a.get("coeff_a"), 1.0),
                    coeff_b=_to_float(a.get("coeff_b"), 0.0),
                    offset=_to_float(a.get("offset"), 0.0),
                    unit=a.get("unit", "°C" if io_type == T_INPUT_TEMP else ""),
                    **common,
                )

            if dev is not None:
                devices.append(dev)

    _LOGGER.info("Calaos import: %d Wago IO points from %s", len(devices), path)
    return devices


def list_hosts(path: str) -> list[str]:
    """Return the distinct PLC hosts referenced in the file."""
    tree = ET.parse(path)
    root = tree.getroot()
    hosts: set[str] = set()
    from .const import WAGO_TYPES

    for el in root.iter():
        if el.get("type") in WAGO_TYPES and el.get("host"):
            hosts.add(el.get("host"))
    return sorted(hosts)
