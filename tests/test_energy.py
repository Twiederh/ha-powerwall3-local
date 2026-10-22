"""Unit tests for the energy accumulator (no Home Assistant needed)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.powerwall3_local.energy import EnergyAccumulator

TZ = ZoneInfo("Europe/Berlin")
GAP = timedelta(minutes=5)


def t(h, m=0, s=0, day=22):
    return datetime(2026, 10, day, h, m, s, tzinfo=TZ)


def test_constant_power_one_hour():
    acc = EnergyAccumulator(max_gap=GAP)
    now = t(12)
    for _ in range(361):  # 10 s steps for one hour
        acc.update(now, 3000)
        now += timedelta(seconds=10)
    assert acc.today_kwh == pytest.approx(3.0, rel=1e-9)
    assert acc.total_kwh == pytest.approx(3.0, rel=1e-9)


def test_trapezoid_ramp():
    acc = EnergyAccumulator(max_gap=GAP)
    acc.update(t(12), 0)
    acc.update(t(12, 1), 1200)  # 60 s, average 600 W -> 0.01 kWh
    assert acc.today_kwh == pytest.approx(0.01)


def test_gap_is_not_integrated():
    acc = EnergyAccumulator(max_gap=GAP)
    acc.update(t(12), 5000)
    acc.update(t(12, 10), 5000)  # 10 min gap > 5 min
    assert acc.today_kwh == 0.0


def test_none_breaks_chain():
    acc = EnergyAccumulator(max_gap=GAP)
    acc.update(t(12), 5000)
    acc.update(t(12, 0, 10), None)
    acc.update(t(12, 0, 20), 5000)
    assert acc.today_kwh == 0.0


def test_negative_power_clamped():
    acc = EnergyAccumulator(max_gap=GAP)
    acc.update(t(12), -50)
    acc.update(t(12, 1), -50)
    assert acc.today_kwh == 0.0


def test_midnight_split_and_reset():
    acc = EnergyAccumulator(max_gap=GAP)
    acc.update(t(23, 59, 30), 3600)
    acc.update(t(0, 0, 30, day=23), 3600)  # 30 s before + 30 s after midnight
    # 30 s at 3600 W = 0.03 kWh belongs to the new day only
    assert acc.today_kwh == pytest.approx(0.03)
    assert acc.total_kwh == pytest.approx(0.06)
    assert acc.day.isoformat() == "2026-10-23"


def test_day_reset_without_samples_overnight():
    acc = EnergyAccumulator(max_gap=GAP)
    acc.update(t(12), 1000)
    acc.update(t(12, 1), 1000)
    assert acc.today_kwh > 0
    acc.update(t(8, day=23), 0)  # first sample next morning
    assert acc.today_kwh == 0.0
    assert acc.total_kwh > 0


def test_restore_same_day_and_next_day():
    acc = EnergyAccumulator(max_gap=GAP, today_kwh=4.2, total_kwh=100.0)
    acc.day = t(12).date()
    data = acc.as_dict()

    same = EnergyAccumulator.from_dict(data, GAP, t(15).date())
    assert same.today_kwh == 4.2 and same.total_kwh == 100.0

    nxt = EnergyAccumulator.from_dict(data, GAP, t(8, day=23).date())
    assert nxt.today_kwh == 0.0 and nxt.total_kwh == 100.0
