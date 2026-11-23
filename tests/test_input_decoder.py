"""Raw edges -> press / release / single / double / triple / long."""
from conftest import load

decoder_mod = load("input_decoder")


class FakeClock:
    """Manual scheduler: timers fire only when the test says so."""

    def __init__(self):
        self.timers = []

    def schedule(self, delay, cb):
        entry = {"delay": delay, "cb": cb, "cancelled": False}
        self.timers.append(entry)

        def cancel():
            entry["cancelled"] = True

        return cancel

    def fire_all(self):
        pending, self.timers = self.timers, []
        for t in pending:
            if not t["cancelled"]:
                t["cb"]()


def make(kind):
    events = []
    clock = FakeClock()
    dec = decoder_mod.InputDecoder(kind, emit=events.append, schedule=clock.schedule)
    return dec, events, clock


def click(dec):
    dec.feed(True)
    dec.feed(False)


def test_bp_single_click():
    dec, events, _ = make("bp")
    click(dec)
    assert events == ["press", "release", "single_click"]


def test_repeated_edge_is_ignored():
    dec, events, _ = make("bp")
    dec.feed(True)
    dec.feed(True)
    dec.feed(False)
    dec.feed(False)
    assert events == ["press", "release", "single_click"]


def test_triple_counts_clicks():
    for n, expected in ((1, "single_click"), (2, "double_click"), (3, "triple_click")):
        dec, events, clock = make("triple")
        for _ in range(n):
            click(dec)
        assert expected not in events  # only after the multi-click gap
        clock.fire_all()
        assert events[-1] == expected


def test_long_press():
    dec, events, clock = make("long")
    dec.feed(True)
    clock.fire_all()  # held past the threshold
    dec.feed(False)
    assert events == ["press", "long_press", "release"]


def test_long_short_click_is_single():
    dec, events, clock = make("long")
    click(dec)
    clock.fire_all()  # cancelled timer must not fire
    assert events == ["press", "release", "single_click"]


def test_event_types():
    assert "triple_click" in make("triple")[0].event_types()
    assert "long_press" in make("long")[0].event_types()
    assert "long_press" not in make("bp")[0].event_types()


def test_cancel_all():
    dec, events, clock = make("triple")
    click(dec)
    dec.cancel_all()
    clock.fire_all()
    assert "single_click" not in events


def test_sync_unsticks_lost_release_silently():
    dec, events, _ = make("bp")
    dec.feed(True)  # the release edge is then lost
    dec._last_edge -= 10  # pretend the press is old (beyond the grace period)
    dec.sync(False)
    assert events == ["press"]  # no fake event emitted
    click(dec)  # the button works again
    assert events[-1] == "single_click"


def test_sync_ignores_recent_edge_and_never_fakes_press():
    dec, events, _ = make("bp")
    dec.feed(True)
    dec.sync(False)  # within the grace period: ignored
    dec.feed(False)
    assert events == ["press", "release", "single_click"]
    dec._last_edge -= 10
    dec.sync(True)  # a closed line is never turned into a press
    assert events == ["press", "release", "single_click"]
