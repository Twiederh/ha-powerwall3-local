"""Blocking wrapper around pypowerwall. All methods must run in an executor."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

import pypowerwall

_LOGGER = logging.getLogger(__name__)


class PowerwallConnectionError(Exception):
    """Raised when the Powerwall cannot be reached or returns no data."""


@dataclass
class StringData:
    """One PV input (MPPT channel) of the Powerwall 3."""

    power: float | None = None
    voltage: float | None = None
    current: float | None = None
    state: str | None = None
    connected: bool | None = None


@dataclass
class PowerwallData:
    """Snapshot of everything one poll returns."""

    strings: dict[str, StringData] = field(default_factory=dict)
    battery_level: float | None = None
    battery_power: float | None = None
    grid_power: float | None = None
    load_power: float | None = None
    site_solar_power: float | None = None
    grid_status: str | None = None

    @property
    def pv_power(self) -> float | None:
        """Sum over all PV strings = output of the integrated PV inverter."""
        values = [s.power for s in self.strings.values() if s.power is not None]
        if not values:
            return None
        return float(sum(max(v, 0.0) for v in values))


@dataclass
class PowerwallInfo:
    """Static device information."""

    din: str | None
    version: str | None
    site_name: str | None


def _to_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


class PowerwallClient:
    """Thin, blocking client. Holds one pypowerwall.Powerwall instance."""

    def __init__(
        self,
        host: str,
        gw_password: str,
        rsa_key_path: str | None,
        timezone: str,
        cache_dir: str,
        timeout: int = 10,
    ) -> None:
        self._host = host
        self._gw_password = gw_password
        self._rsa_key_path = rsa_key_path or None
        self._timezone = timezone
        self._cache_dir = cache_dir
        self._timeout = timeout
        self._pw: pypowerwall.Powerwall | None = None

    # -- connection -------------------------------------------------------

    def connect(self) -> None:
        """Create the pypowerwall instance (connects in the constructor)."""
        pw = pypowerwall.Powerwall(
            host=self._host,
            password="",
            email="nobody@nowhere.com",
            timezone=self._timezone,
            pwcacheexpire=2,
            timeout=self._timeout,
            authpath=self._cache_dir,
            cachefile=f"{self._cache_dir}/.powerwall",
            gw_pwd=self._gw_password,
            rsa_key_path=self._rsa_key_path,
            failover=False,  # never fall back to Tesla cloud modes
        )
        if pw.client is None:
            raise PowerwallConnectionError(
                f"Unable to connect to Powerwall at {self._host}"
            )
        self._pw = pw

    def _ensure_connected(self) -> pypowerwall.Powerwall:
        if self._pw is None:
            self.connect()
        elif self._pw.client is None and not self._pw.connect():
            raise PowerwallConnectionError(
                f"Unable to reconnect to Powerwall at {self._host}"
            )
        assert self._pw is not None
        return self._pw

    # -- data -------------------------------------------------------------

    def get_info(self) -> PowerwallInfo:
        """Return static device info (DIN, firmware, site name)."""
        pw = self._ensure_connected()
        din = pw.din()
        if not din:
            raise PowerwallConnectionError("Powerwall returned no DIN")
        version = pw.version()
        return PowerwallInfo(
            din=str(din),
            version=str(version) if version else None,
            site_name=pw.site_name(),
        )

    def fetch(self) -> PowerwallData:
        """Poll strings and site values."""
        pw = self._ensure_connected()

        try:
            raw_strings = pw.strings() or {}
        except Exception as err:  # noqa: BLE001 - pypowerwall raises broadly
            self._pw = None
            raise PowerwallConnectionError(f"Reading PV strings failed: {err}") from err
        if not raw_strings:
            # Force a reconnect on the next poll
            self._pw = None
            raise PowerwallConnectionError("Powerwall returned no PV string data")

        strings: dict[str, StringData] = {}
        for name, values in sorted(raw_strings.items()):
            if not isinstance(values, dict):
                continue
            strings[str(name)] = StringData(
                power=_to_float(values.get("Power")),
                voltage=_to_float(values.get("Voltage")),
                current=_to_float(values.get("Current")),
                state=values.get("State"),
                connected=values.get("Connected"),
            )

        # Site values are a bonus - a failure here must not drop the string data
        power: dict[str, Any] = {}
        level = grid_status = None
        try:
            power = pw.power() or {}
        except Exception as err:  # noqa: BLE001 - pypowerwall raises broadly
            _LOGGER.debug("power() failed: %s", err)
        try:
            level = pw.level(scale=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("level() failed: %s", err)
        try:
            grid_status = pw.grid_status()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("grid_status() failed: %s", err)

        return PowerwallData(
            strings=strings,
            battery_level=_to_float(level),
            battery_power=_to_float(power.get("battery")),
            grid_power=_to_float(power.get("site")),
            load_power=_to_float(power.get("load")),
            site_solar_power=_to_float(power.get("solar")),
            grid_status=grid_status,
        )
