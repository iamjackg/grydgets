"""Tests for grydgets/appearance.py -- picking a theme from the sun.

The reference times come from astral itself rather than being written out as
literals: what's under test is the offset arithmetic and the ordering of
boundaries around midnight, not astral's ephemeris. They are asked for in the
same longitude-derived zone the module buckets dates by, so that a date holds
exactly one sunrise and one sunset.

Run with: uv run --with pytest python -m pytest tests/test_appearance.py
"""

from datetime import date, datetime, timedelta, timezone

import pytest
import voluptuous
from astral import Observer
from astral.sun import sunrise, sunset

from grydgets import appearance, config
from grydgets.appearance import DAY, NIGHT, SunSchedule

# Far enough west that its sunset and the following sunrise fall
# either side of a UTC midnight, which is the case the module is built around.
LAT, LON = 45.12, -75.34
OBSERVER = Observer(latitude=LAT, longitude=LON)
SOLAR = timezone(timedelta(hours=LON / 15))
SUMMER = date(2026, 8, 9)


def sun_times(day=SUMMER):
    """The daylight interval of solar date ``day``, in UTC."""
    return (
        sunrise(OBSERVER, day, tzinfo=SOLAR).astimezone(timezone.utc),
        sunset(OBSERVER, day, tzinfo=SOLAR).astimezone(timezone.utc),
    )


def minutes(n):
    return timedelta(minutes=n)


# --- the basic day/night split -------------------------------------------


def test_midday_is_day_and_the_small_hours_are_night():
    schedule = SunSchedule(LAT, LON)
    rise, set_ = sun_times()
    assert schedule.mode_at(rise + minutes(1)) == DAY
    assert schedule.mode_at(set_ - minutes(1)) == DAY
    assert schedule.mode_at(rise - minutes(1)) == NIGHT
    assert schedule.mode_at(set_ + minutes(1)) == NIGHT


def test_the_boundary_instant_itself_belongs_to_the_mode_it_starts():
    schedule = SunSchedule(LAT, LON)
    rise, set_ = sun_times()
    assert schedule.mode_at(rise) == DAY
    assert schedule.mode_at(set_) == NIGHT


def test_night_holds_across_utc_midnight():
    """The hours after 00:00 UTC are the previous local evening here, so a
    schedule that only looked at today's boundaries would get this wrong."""
    schedule = SunSchedule(LAT, LON)
    rise, set_ = sun_times()
    # The premise: this day's sunset is on the UTC date after its sunrise.
    assert set_.date() > rise.date()
    # An hour before that sunset is still daylight, on a UTC date whose own
    # sunrise is ten hours away.
    assert schedule.mode_at(set_ - minutes(60)) == DAY
    assert schedule.mode_at(set_ + minutes(60)) == NIGHT


# --- offsets --------------------------------------------------------------


def test_a_negative_sunset_offset_brings_night_forward():
    schedule = SunSchedule(LAT, LON, sunset_offset=-30)
    _, set_ = sun_times()
    assert schedule.mode_at(set_ - minutes(40)) == DAY
    assert schedule.mode_at(set_ - minutes(20)) == NIGHT


def test_a_positive_sunrise_offset_holds_night_later():
    schedule = SunSchedule(LAT, LON, sunrise_offset=45)
    rise, _ = sun_times()
    assert schedule.mode_at(rise + minutes(30)) == NIGHT
    assert schedule.mode_at(rise + minutes(50)) == DAY


def test_each_offset_moves_only_its_own_boundary():
    schedule = SunSchedule(LAT, LON, sunset_offset=-30)
    rise, _ = sun_times()
    assert schedule.mode_at(rise + minutes(1)) == DAY
    assert schedule.mode_at(rise - minutes(1)) == NIGHT


# --- what comes next ------------------------------------------------------


def test_next_change_is_the_first_boundary_still_ahead():
    schedule = SunSchedule(LAT, LON)
    rise, set_ = sun_times()
    when, mode = schedule.next_change(rise + minutes(1))
    assert (when, mode) == (set_, NIGHT)
    when, mode = schedule.next_change(rise - minutes(1))
    assert (when, mode) == (rise, DAY)


def test_next_change_reaches_into_tomorrow():
    schedule = SunSchedule(LAT, LON)
    _, set_ = sun_times()
    when, mode = schedule.next_change(set_ + minutes(1))
    assert mode == DAY
    assert when > set_


def test_every_evening_gets_its_own_sunset():
    """At a longitude where sunset sits within a minute of 00:00 UTC, bucketing
    dates by UTC drops one evening's sunset entirely and the theme stays on day
    right through that night."""
    schedule = SunSchedule(43.15, -79.24)
    for day in range(24, 31):
        # 21:00 EDT, an hour past the latest sunset in this week.
        evening = datetime(2026, 8, day, 1, tzinfo=timezone.utc) + timedelta(days=1)
        assert schedule.mode_at(evening) == NIGHT, f"2026-08-{day} evening"


# --- the sun refusing to co-operate --------------------------------------


@pytest.mark.parametrize(
    "when", [datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
             datetime(2026, 12, 21, 12, tzinfo=timezone.utc)]
)
def test_polar_day_and_polar_night_report_nothing_rather_than_guessing(when):
    """Svalbard in midsummer and midwinter: no sunrise, no sunset, so there is
    no answer -- and the caller is expected to keep whatever theme is up."""
    schedule = SunSchedule(78.22, 15.65)
    assert schedule.mode_at(when) is None
    assert schedule.next_change(when) is None


def test_a_polar_location_still_switches_once_the_sun_returns():
    schedule = SunSchedule(78.22, 15.65)
    assert schedule.mode_at(datetime(2026, 4, 15, 12, tzinfo=timezone.utc)) == DAY


def test_the_day_window_runs_forwards_from_an_evening_instant():
    """Asking at 18:35 local must give this morning's sunrise and tonight's
    sunset, not this morning's sunrise and last night's."""
    schedule = SunSchedule(LAT, LON, sunset_offset=-30)
    rise, set_ = sun_times()
    start, end = schedule.day_window(set_ - minutes(80))
    assert start == rise
    assert end == set_ - minutes(30)
    assert start < end


def test_the_day_window_after_dark_describes_the_day_just_gone():
    schedule = SunSchedule(LAT, LON)
    rise, set_ = sun_times()
    start, end = schedule.day_window(set_ + minutes(30))
    assert (start, end) == (rise, set_)


def test_describe_names_the_place_the_times_and_what_happens_next():
    schedule = SunSchedule(LAT, LON, sunset_offset=-30)
    line = schedule.describe(datetime(2026, 8, 9, 12, tzinfo=timezone.utc))
    assert "45.12,-75.34" in line
    assert "+0/-30 min" in line
    assert "night theme at" in line


def test_describe_says_so_when_nothing_is_going_to_happen():
    schedule = SunSchedule(78.22, 15.65)
    line = schedule.describe(datetime(2026, 6, 21, 12, tzinfo=timezone.utc))
    assert "no theme change due" in line


# --- reading the conf.yaml block -----------------------------------------


APPEARANCE = {
    "latitude": LAT,
    "longitude": LON,
    "themes": {"day": "themes/light.yaml", "night": "themes/dark.yaml"},
    "offsets": {"sunrise": 10, "sunset": -30},
}


def test_from_config_carries_the_offsets_through():
    schedule = SunSchedule.from_config(APPEARANCE)
    assert schedule.sunrise_offset == minutes(10)
    assert schedule.sunset_offset == minutes(-30)


def test_offsets_are_optional():
    conf = {k: v for k, v in APPEARANCE.items() if k != "offsets"}
    schedule = SunSchedule.from_config(conf)
    assert schedule.sunrise_offset == timedelta(0)
    assert schedule.sunset_offset == timedelta(0)


def test_two_themes_without_coordinates_mean_no_schedule():
    """A block naming themes but no location switches only over HTTP."""
    conf = {"themes": APPEARANCE["themes"]}
    validated = voluptuous.Schema(config.appearance_schema)(conf)
    assert SunSchedule.from_config(validated) is None


def test_half_a_location_is_rejected_rather_than_read_as_manual_only():
    conf = {"themes": APPEARANCE["themes"], "latitude": LAT}
    with pytest.raises(voluptuous.Invalid) as excinfo:
        config._validate_appearance(conf)
    assert "no longitude" in str(excinfo.value)


def test_the_starting_theme_defaults_to_day_and_can_be_night():
    conf = {"themes": APPEARANCE["themes"]}
    assert voluptuous.Schema(config.appearance_schema)(conf)["default"] == "day"
    conf = dict(conf, default="night")
    assert voluptuous.Schema(config.appearance_schema)(conf)["default"] == "night"
    with pytest.raises(voluptuous.Invalid):
        voluptuous.Schema(config.appearance_schema)(dict(conf, default="dusk"))


def test_the_schema_accepts_a_whole_appearance_block():
    validated = voluptuous.Schema(config.appearance_schema)(dict(APPEARANCE))
    assert validated["offsets"]["sunset"] == -30


def test_the_schema_fills_in_a_missing_offset():
    conf = dict(APPEARANCE, offsets={"sunset": -30})
    validated = voluptuous.Schema(config.appearance_schema)(conf)
    assert validated["offsets"]["sunrise"] == 0


@pytest.mark.parametrize(
    "broken, why",
    [
        ({"latitude": 100.0}, "a latitude off the planet"),
        ({"longitude": -900.0}, "a longitude off the planet"),
        ({"themes": {"day": "themes/light.yaml"}}, "only one theme named"),
        ({"offsets": {"sunrise": 5000}}, "an offset longer than half a day"),
        ({"offsets": {"sunrise": "an hour"}}, "an offset that isn't a number"),
    ],
)
def test_the_schema_rejects(broken, why):
    conf = dict(APPEARANCE, **broken)
    with pytest.raises(voluptuous.Invalid):
        voluptuous.Schema(config.appearance_schema)(conf)


def test_a_conf_file_without_an_appearance_block_is_still_valid(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text(
        "graphics:\n  resolution: [480, 320]\n  fps-limit: 10\n"
        "logging:\n  level: info\nserver:\n  port: 5000\n"
    )
    assert "appearance" not in config.load_config(str(path))


def test_a_conf_file_with_an_appearance_block_loads(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text(
        "graphics:\n  resolution: [480, 320]\n  fps-limit: 10\n"
        "logging:\n  level: info\nserver:\n  port: 5000\n"
        "appearance:\n"
        f"  latitude: {LAT}\n  longitude: {LON}\n"
        "  themes:\n    day: themes/light.yaml\n    night: themes/dark.yaml\n"
        "  offsets:\n    sunset: -30\n"
    )
    loaded = config.load_config(str(path))
    assert loaded["appearance"]["themes"]["night"] == "themes/dark.yaml"
    assert appearance.SunSchedule.from_config(loaded["appearance"])
