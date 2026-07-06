"""Data models describing Wago IO points parsed from a Calaos configuration."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WagoIO:
    """Base description of one Wago IO point."""

    io_id: str          # unique id (Calaos id, e.g. "output_28")
    name: str
    io_type: str        # Calaos type, e.g. "WODigital"
    host: str
    room: str = ""
    enabled: bool = True
    extra: dict = field(default_factory=dict)


@dataclass
class DigitalInput(WagoIO):
    """A digital input (push button / switch)."""

    var: int = 0
    kind: str = "bp"    # "bp" | "triple" | "long"
    knx: bool = False


@dataclass
class DigitalOutput(WagoIO):
    """A simple relay / light on-off output."""

    var: int = 0
    wago_841: bool = True
    knx: bool = False
    as_light: bool = True   # True -> light platform, False -> switch platform


@dataclass
class ShutterOutput(WagoIO):
    """A roller shutter driven by two coils (up/down) with timed positioning."""

    var_up: int = 0
    var_down: int = 0
    time_up: float = 30.0     # seconds for a full open
    time_down: float = 30.0   # seconds for a full close
    wago_841: bool = True


@dataclass
class DaliChannel:
    """One DALI/DMX channel."""

    line: int = 1
    address: int = 1
    group: int = 0
    fade_time: int = 1


@dataclass
class DaliOutput(WagoIO):
    """A single (mono) DALI/DMX dimmable light."""

    channel: DaliChannel = field(default_factory=DaliChannel)


@dataclass
class DaliRGBOutput(WagoIO):
    """An RGB DALI/DMX light (three channels)."""

    red: DaliChannel = field(default_factory=DaliChannel)
    green: DaliChannel = field(default_factory=DaliChannel)
    blue: DaliChannel = field(default_factory=DaliChannel)


@dataclass
class AnalogInput(WagoIO):
    """A temperature (PT100/PT1000) or generic analog input."""

    var: int = 0
    is_temp: bool = True
    coeff_a: float = 1.0     # value = coeff_a * raw + coeff_b (applied after /10 for temp)
    coeff_b: float = 0.0
    offset: float = 0.0
    unit: str = ""
