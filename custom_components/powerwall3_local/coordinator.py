"""Data update coordinator for Powerwall 3 Local."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import PowerwallClient, PowerwallConnectionError, PowerwallData, PowerwallInfo
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_INTEGRATION_GAP,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
    TOTAL_KEY,
)
from .energy import EnergyAccumulator

_LOGGER = logging.getLogger(__name__)

type Powerwall3ConfigEntry = ConfigEntry[Powerwall3Coordinator]


class Powerwall3Coordinator(DataUpdateCoordinator[PowerwallData]):
    """Polls the Powerwall and integrates PV power into energy."""

    config_entry: Powerwall3ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Powerwall3ConfigEntry,
        client: PowerwallClient,
        info: PowerwallInfo,
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.info = info
        self.energy: dict[str, EnergyAccumulator] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.energy"
        )

    async def async_load_energy(self) -> None:
        """Restore energy counters from storage."""
        stored = await self._store.async_load() or {}
        today = dt_util.now().date()
        for key, data in stored.get("counters", {}).items():
            self.energy[key] = EnergyAccumulator.from_dict(data, MAX_INTEGRATION_GAP, today)

    def _energy_data_to_save(self) -> dict[str, Any]:
        return {"counters": {key: acc.as_dict() for key, acc in self.energy.items()}}

    async def async_save_energy(self) -> None:
        """Write energy counters immediately (on unload/shutdown)."""
        await self._store.async_save(self._energy_data_to_save())

    def _accumulator(self, key: str) -> EnergyAccumulator:
        if key not in self.energy:
            self.energy[key] = EnergyAccumulator(max_gap=MAX_INTEGRATION_GAP)
        return self.energy[key]

    async def _async_update_data(self) -> PowerwallData:
        now = dt_util.now()
        try:
            data = await self.hass.async_add_executor_job(self.client.fetch)
        except PowerwallConnectionError as err:
            # Break every integration chain - an outage must not create energy
            for acc in self.energy.values():
                acc.update(now, None)
            raise UpdateFailed(str(err)) from err

        for name, string in data.strings.items():
            self._accumulator(name).update(now, string.power)
        self._accumulator(TOTAL_KEY).update(now, data.pv_power)

        self._store.async_delay_save(self._energy_data_to_save, STORAGE_SAVE_DELAY)
        return data
