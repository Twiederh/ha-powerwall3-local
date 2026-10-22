"""Energy accumulation (power -> kWh) without Home Assistant dependencies.

Integrates power readings with the trapezoidal rule and keeps two counters:
- ``today``: resets at local midnight
- ``total``: lifetime counter, never resets

Gaps longer than ``max_gap`` (e.g. the Powerwall was unreachable) are not
integrated, so an outage never invents energy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


@dataclass
class EnergyAccumulator:
    """Integrates power (W) into energy (kWh) for one source."""

    max_gap: timedelta
    today_kwh: float = 0.0
    total_kwh: float = 0.0
    day: date | None = None
    last_time: datetime | None = None
    last_power_w: float | None = None

    def update(self, now: datetime, power_w: float | None) -> None:
        """Add a power sample taken at ``now`` (timezone-aware, local time)."""
        today = now.date()
        if self.day is None:
            self.day = today

        if power_w is None:
            # No valid reading: break the integration chain
            self.last_time = None
            self.last_power_w = None
            self._roll_day(today)
            return

        power_w = max(float(power_w), 0.0)  # PV never consumes energy

        if self.last_time is not None and self.last_power_w is not None:
            delta = now - self.last_time
            if timedelta(0) < delta <= self.max_gap:
                if self.last_time.date() == today:
                    self._add(self.last_power_w, power_w, delta)
                else:
                    # Interval crosses midnight: split at local midnight
                    midnight = datetime.combine(today, datetime.min.time(), tzinfo=now.tzinfo)
                    before = midnight - self.last_time
                    after = now - midnight
                    frac = before / delta
                    p_mid = self.last_power_w + (power_w - self.last_power_w) * frac
                    self._add(self.last_power_w, p_mid, before)
                    self._roll_day(today)
                    self._add(p_mid, power_w, after)

        self._roll_day(today)
        self.last_time = now
        self.last_power_w = power_w

    def _add(self, p1: float, p2: float, delta: timedelta) -> None:
        kwh = (p1 + p2) / 2.0 * delta.total_seconds() / 3_600_000.0
        self.today_kwh += kwh
        self.total_kwh += kwh

    def _roll_day(self, today: date) -> None:
        if self.day != today:
            self.day = today
            self.today_kwh = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Serialize the persistent part (counters, not the integration chain)."""
        return {
            "today_kwh": self.today_kwh,
            "total_kwh": self.total_kwh,
            "day": self.day.isoformat() if self.day else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], max_gap: timedelta, today: date) -> EnergyAccumulator:
        """Restore counters; ``today`` is dropped if it belongs to an earlier day."""
        acc = cls(max_gap=max_gap)
        acc.total_kwh = float(data.get("total_kwh") or 0.0)
        stored_day = data.get("day")
        if stored_day and date.fromisoformat(stored_day) == today:
            acc.today_kwh = float(data.get("today_kwh") or 0.0)
        acc.day = today
        return acc
