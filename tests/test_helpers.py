"""Address translation (must match calaos_base) and cover reversal pause."""
from conftest import load

helpers = load("helpers")
const = load("const")


def test_output_address_841():
    assert helpers.output_address(5, wago_841=True) == 5 + 4096


def test_output_address_842():
    assert helpers.output_address(5, wago_841=False) == 5


def test_output_address_knx_never_gets_841_offset():
    assert helpers.output_address(5, wago_841=True, knx=True) == 5 + 6144
    assert helpers.output_address(5, wago_841=False, knx=True) == 5 + 6144


def test_readback_base_includes_knx_but_never_841():
    assert helpers.readback_base(3) == 3
    assert helpers.readback_base(3, knx=True) == 3 + 6144


def test_readback_addresses():
    assert helpers.readback_addresses(3) == (3 + 0x200, 3)
    base = helpers.readback_base(3, knx=True)
    assert helpers.readback_addresses(base) == (3 + 6144 + 0x200, 3 + 6144)


def test_reverse_wait_same_direction_or_first_move():
    assert helpers.reverse_wait(None, 0.0, "open", 100.0) == 0.0
    assert helpers.reverse_wait("open", 99.9, "open", 100.0) == 0.0


def test_reverse_wait_opposite_direction():
    delay = const.COVER_REVERSE_DELAY
    # stopped just now -> full pause
    assert helpers.reverse_wait("close", 100.0, "open", 100.0) == delay
    # stopped a bit earlier -> remaining part only
    assert abs(helpers.reverse_wait("close", 100.0, "open", 100.2) - (delay - 0.2)) < 1e-9
    # stopped long ago -> no pause
    assert helpers.reverse_wait("close", 0.0, "open", 100.0) == 0.0
