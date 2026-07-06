"""Decode raw digital-input edges into click / double / triple / long events.

The Wago PLC only reports raw rising/falling edges over UDP
(``WAGO INT <var> <0|1>``). Calaos interprets those edges server-side into
button semantics; this module reproduces that interpretation so Home Assistant
can expose meaningful events.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from .const import (
    EV_DOUBLE,
    EV_LONG,
    EV_PRESS,
    EV_RELEASE,
    EV_SINGLE,
    EV_TRIPLE,
)


class InputDecoder:
    """State machine turning raw edges into higher-level button events.

    One decoder per digital input. ``kind`` selects the behaviour:

    * ``"bp"``     - simple button: fires ``press`` / ``release`` and a
      ``single_click`` on release.
    * ``"triple"`` - counts clicks inside a window and fires
      ``single_click`` / ``double_click`` / ``triple_click``.
    * ``"long"``   - distinguishes a ``single_click`` from a ``long_press``.
    """

    def __init__(
        self,
        kind: str,
        emit: Callable[[str], None],
        schedule: Callable[[float, Callable[[], None]], Callable[[], None]],
        multi_click_ms: int = 350,
        long_press_ms: int = 500,
    ) -> None:
        self._kind = kind
        self._emit = emit
        # schedule(delay_seconds, callback) -> cancel handle
        self._schedule = schedule
        self._multi_gap = multi_click_ms / 1000.0
        self._long_delay = long_press_ms / 1000.0

        self._pressed = False
        self._click_count = 0
        self._press_time = 0.0
        self._long_fired = False
        self._cancel_multi: Callable[[], None] | None = None
        self._cancel_long: Callable[[], None] | None = None

    # -- helpers --------------------------------------------------------------
    def _cancel(self, handle_attr: str) -> None:
        handle = getattr(self, handle_attr)
        if handle is not None:
            try:
                handle()
            except Exception:  # noqa: BLE001 - cancelling a fired timer is harmless
                pass
            setattr(self, handle_attr, None)

    # -- public API -----------------------------------------------------------
    def feed(self, state: bool) -> None:
        """Feed a raw edge (True = pressed / closed, False = released)."""
        if state and not self._pressed:
            self._on_press()
        elif not state and self._pressed:
            self._on_release()

    def _on_press(self) -> None:
        self._pressed = True
        self._press_time = time.monotonic()
        self._emit(EV_PRESS)

        if self._kind == "long":
            self._long_fired = False
            self._cancel("_cancel_long")

            def _fire_long() -> None:
                self._cancel_long = None
                if self._pressed:
                    self._long_fired = True
                    self._emit(EV_LONG)

            self._cancel_long = self._schedule(self._long_delay, _fire_long)

        elif self._kind == "triple":
            # a new press cancels the pending multi-click flush
            self._cancel("_cancel_multi")

    def _on_release(self) -> None:
        self._pressed = False
        self._emit(EV_RELEASE)
        self._cancel("_cancel_long")

        if self._kind == "long":
            if not self._long_fired:
                self._emit(EV_SINGLE)
            return

        if self._kind == "bp":
            self._emit(EV_SINGLE)
            return

        # triple: accumulate clicks then flush after the gap
        self._click_count += 1
        self._cancel("_cancel_multi")

        def _flush() -> None:
            self._cancel_multi = None
            count = self._click_count
            self._click_count = 0
            if count >= 3:
                self._emit(EV_TRIPLE)
            elif count == 2:
                self._emit(EV_DOUBLE)
            else:
                self._emit(EV_SINGLE)

        self._cancel_multi = self._schedule(self._multi_gap, _flush)

    def event_types(self) -> list[str]:
        """Return the event types this decoder can emit (for the event entity)."""
        base = [EV_PRESS, EV_RELEASE, EV_SINGLE]
        if self._kind == "triple":
            base += [EV_DOUBLE, EV_TRIPLE]
        elif self._kind == "long":
            base += [EV_LONG]
        return base
