"""Load the Home-Assistant-free modules of the integration for unit tests.

``custom_components/wago2haddon/__init__.py`` imports Home Assistant, so the
package itself is not imported. Instead a bare package object pointing at the
same folder is registered as ``w2h``; its submodules can then be imported
(relative imports such as ``from .const import ...`` keep working) without
executing ``__init__.py``.

Only modules that do not import ``homeassistant`` can be loaded this way:
const, models, helpers, modbus_tcp, input_decoder, calaos_import.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "wago2haddon"

if "w2h" not in sys.modules:
    _pkg = types.ModuleType("w2h")
    _pkg.__path__ = [str(COMPONENT_DIR)]  # type: ignore[attr-defined]
    sys.modules["w2h"] = _pkg


def load(name: str):
    """Import ``w2h.<name>`` (a HA-free module of the integration)."""
    return importlib.import_module(f"w2h.{name}")


@pytest.fixture
def w2h():
    return load
