"""The Powerwall 3 Local integration (local PV string data via pypowerwall)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import PowerwallClient, PowerwallConnectionError
from .const import CONF_GW_PASSWORD, CONF_RSA_KEY_PATH, DOMAIN
from .coordinator import Powerwall3ConfigEntry, Powerwall3Coordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


def build_client(hass: HomeAssistant, data: dict) -> PowerwallClient:
    """Create a client from config entry data."""
    return PowerwallClient(
        host=data[CONF_HOST],
        gw_password=data[CONF_GW_PASSWORD],
        rsa_key_path=data.get(CONF_RSA_KEY_PATH) or None,
        timezone=str(hass.config.time_zone),
        cache_dir=hass.config.path(".storage"),
    )


async def async_setup_entry(hass: HomeAssistant, entry: Powerwall3ConfigEntry) -> bool:
    """Set up Powerwall 3 Local from a config entry."""
    client = build_client(hass, dict(entry.data))
    try:
        info = await hass.async_add_executor_job(client.get_info)
    except PowerwallConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = Powerwall3Coordinator(hass, entry, client, info)
    await coordinator.async_load_energy()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Powerwall3ConfigEntry) -> bool:
    """Unload a config entry and persist the energy counters."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save_energy()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: Powerwall3ConfigEntry) -> None:
    """Reload when options (scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


__all__ = ["DOMAIN"]
