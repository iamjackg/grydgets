"""Choosing between a day theme and a night theme by the sun.

``conf.yaml``'s ``appearance:`` block names two theme files and a location::

    appearance:
      latitude: 45.12
      longitude: -75.34
      themes:
        day: themes/day.yaml
        night: themes/night.yaml
      offsets:
        sunrise: 0
        sunset: -30

Each offset is in minutes and moves that boundary only.

Everything here works in UTC; local time appears only in
:meth:`SunSchedule.describe`, for the log line.

The mode is read off a list of transitions rather than by asking "is now
between today's sunrise and today's sunset". Those two can fall either side of
a UTC midnight, and an offset can push a boundary across the date line, so
taking the most recent transition from yesterday, today and tomorrow avoids
the ordering problem at every longitude.
"""

from __future__ import annotations

from datetime import date as date_type, datetime, timedelta, timezone

try:
    from astral import Observer
    from astral.sun import sunrise, sunset
except ImportError:  # pragma: no cover - exercised only on an old install
    Observer = None

DAY = "day"
NIGHT = "night"
MODES = (DAY, NIGHT)


class AppearanceError(Exception):
    """The ``appearance:`` block can't be used as written."""


class SunSchedule:
    """Sunrise and sunset for one location, with a per-boundary offset."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        sunrise_offset: int = 0,
        sunset_offset: int = 0,
    ) -> None:
        if Observer is None:
            raise AppearanceError(
                "conf.yaml configures 'appearance:', which needs the astral "
                "package to work out sunrise and sunset. Install it "
                "(uv sync, or pip install astral) or remove the block."
            )
        self.latitude = latitude
        self.longitude = longitude
        self.sunrise_offset = timedelta(minutes=sunrise_offset)
        self.sunset_offset = timedelta(minutes=sunset_offset)
        self._observer = Observer(latitude=latitude, longitude=longitude)

    @classmethod
    def from_config(cls, appearance_conf: dict) -> SunSchedule | None:
        """The schedule an ``appearance:`` block asks for, or ``None`` if it
        gave no coordinates -- meaning nothing switches by itself and the
        theme is whatever the HTTP endpoint last said."""
        if "latitude" not in appearance_conf:
            return None
        offsets = appearance_conf.get("offsets") or {}
        return cls(
            latitude=appearance_conf["latitude"],
            longitude=appearance_conf["longitude"],
            sunrise_offset=offsets.get("sunrise", 0),
            sunset_offset=offsets.get("sunset", 0),
        )

    def _boundary(self, which: str, day: date_type) -> datetime | None:
        """One boundary for one UTC date, or ``None`` where there isn't one.

        Above the polar circles the sun can fail to rise or set at all, which
        astral reports by raising. Sunrise and sunset are asked for separately
        so that a day with one but not the other still contributes what it has.
        """
        compute, offset = (
            (sunrise, self.sunrise_offset)
            if which == DAY
            else (sunset, self.sunset_offset)
        )
        try:
            return compute(self._observer, day, tzinfo=timezone.utc) + offset
        except ValueError:
            return None

    def transitions(self, around: datetime) -> list[tuple[datetime, str]]:
        """Every mode change in the three UTC days centred on ``around``,
        in order. Each entry is the instant the named mode starts."""
        changes = []
        for day_offset in (-1, 0, 1):
            day = (around + timedelta(days=day_offset)).date()
            for mode in MODES:
                when = self._boundary(mode, day)
                if when is not None:
                    changes.append((when, mode))
        changes.sort()
        return changes

    def mode_at(self, now: datetime | None = None) -> str | None:
        """Which theme should be showing, or ``None`` if the sun neither rose
        nor set anywhere near ``now`` and there is nothing to go on."""
        now = now or datetime.now(timezone.utc)
        current = None
        for when, mode in self.transitions(now):
            if when > now:
                break
            current = mode
        return current

    def next_change(self, now: datetime | None = None) -> tuple[datetime, str] | None:
        """The next transition after ``now``, or ``None`` if there isn't one
        within the window."""
        now = now or datetime.now(timezone.utc)
        for when, mode in self.transitions(now):
            if when > now:
                return when, mode
        return None

    def day_window(
        self, now: datetime | None = None
    ) -> tuple[datetime | None, datetime | None]:
        """The daylight interval ``now`` is in, or the most recent one behind
        it. ``(None, None)`` where the sun does neither.

        Taken off the transition list rather than by asking for sunrise and
        sunset on the same date: west of Greenwich those two are not the same
        day's daylight -- the sunset astral reports for a date is the end of
        the *previous* local evening, hours before that date's sunrise -- so
        pairing them shows a window that runs backwards.
        """
        now = now or datetime.now(timezone.utc)
        changes = self.transitions(now)
        starts = [when for when, mode in changes if mode == DAY]
        past = [when for when in starts if when <= now]
        start = past[-1] if past else (starts[0] if starts else None)
        if start is None:
            return None, None
        ends = [when for when, mode in changes if mode == NIGHT and when > start]
        return start, (ends[0] if ends else None)

    def describe(self, now: datetime | None = None) -> str:
        """A log line saying what the sun is doing and when the theme changes
        next, in the reader's local time.

        Worth printing at startup because it's the only way to tell wrong
        coordinates from broken switching: both look like a dashboard that
        stays on one theme.
        """
        now = now or datetime.now(timezone.utc)
        start, end = self.day_window(now)

        def clock(when: datetime | None) -> str:
            return when.astimezone().strftime("%H:%M") if when else "never"

        offsets = "{:+d}/{:+d} min".format(
            int(self.sunrise_offset.total_seconds() // 60),
            int(self.sunset_offset.total_seconds() // 60),
        )
        line = (
            f"Sun at {self.latitude},{self.longitude}: day from {clock(start)} "
            f"to {clock(end)} local (offsets {offsets})"
        )
        upcoming = self.next_change(now)
        if upcoming is None:
            return f"{line}; no theme change due"
        when, mode = upcoming
        return f"{line}; {mode} theme at {clock(when)}"
