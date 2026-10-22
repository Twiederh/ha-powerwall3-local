"""Integration tests with a mocked pypowerwall (pytest-homeassistant-custom-component)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powerwall3_local.const import (
    CONF_CONNECTION_TYPE,
    CONF_GW_PASSWORD,
    CONF_RSA_KEY_PATH,
    CONNECTION_WIFI,
    DOMAIN,
)

DIN = "1707000-11-M--TG1234567890TB"

STRINGS = {
    "A": {"Connected": True, "Current": 8.0, "Power": 2400.0, "State": "Pv_Active", "Voltage": 300.0},
    "B": {"Connected": True, "Current": 8.0, "Power": 2400.0, "State": "Pv_Active_Parallel", "Voltage": 300.0},
    "C": {"Connected": True, "Current": 5.0, "Power": 1350.0, "State": "Pv_Active", "Voltage": 270.0},
    "D": {"Connected": False, "Current": 0, "Power": 0, "State": "Pv_Standby", "Voltage": 0},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def make_pw(strings=STRINGS):
    pw = MagicMock()
    pw.client = object()
    pw.din.return_value = DIN
    pw.version.return_value = "25.36.2"
    pw.site_name.return_value = "Zuhause"
    pw.strings.return_value = strings
    pw.power.return_value = {"site": -1500.0, "solar": 9000.0, "battery": -2000.0, "load": 800.0}
    pw.level.return_value = 63.5
    pw.grid_status.return_value = "UP"
    return pw


async def test_config_flow_wifi(hass: HomeAssistant) -> None:
    with patch("custom_components.powerwall3_local.api.pypowerwall.Powerwall", return_value=make_pw()):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONNECTION_TYPE: CONNECTION_WIFI}
        )
        assert result["step_id"] == "connection"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.91.1", CONF_GW_PASSWORD: "ABCDEFGHIJ"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "Zuhause"
        assert result["result"].unique_id == DIN
        await hass.async_block_till_done()


async def test_config_flow_v1r_missing_key(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CONNECTION_TYPE: "v1r"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "10.42.1.40", CONF_GW_PASSWORD: "ABCDEFGHIJ", CONF_RSA_KEY_PATH: "/nope/key.pem"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_RSA_KEY_PATH: "invalid_key_path"}


async def test_config_flow_cannot_connect(hass: HomeAssistant) -> None:
    pw = make_pw()
    pw.client = None
    with patch("custom_components.powerwall3_local.api.pypowerwall.Powerwall", return_value=pw):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONNECTION_TYPE: CONNECTION_WIFI}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.91.1", CONF_GW_PASSWORD: "x"}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_sensors_and_energy(hass: HomeAssistant, freezer) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DIN,
        data={CONF_CONNECTION_TYPE: CONNECTION_WIFI, CONF_HOST: "192.168.91.1",
              CONF_GW_PASSWORD: "ABCDEFGHIJ", CONF_RSA_KEY_PATH: ""},
        options={"scan_interval": 10},
    )
    entry.add_to_hass(hass)
    freezer.move_to("2026-10-22T10:00:00+00:00")  # noon in Berlin, far from midnight
    pw = make_pw()
    with patch("custom_components.powerwall3_local.api.pypowerwall.Powerwall", return_value=pw):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        pv = hass.states.get("sensor.zuhause_pv_power")
        assert pv is not None, sorted(hass.states.async_entity_ids("sensor"))
        assert float(pv.state) == 6150.0
        assert float(hass.states.get("sensor.zuhause_string_a_power").state) == 2400.0
        assert hass.states.get("sensor.zuhause_battery_level").state == "63.5"

        # Advance one hour in 10 s steps -> 6.15 kWh in total
        coordinator = entry.runtime_data
        for _ in range(360):
            freezer.tick(timedelta(seconds=10))
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        today = float(hass.states.get("sensor.zuhause_pv_energy_today").state)
        assert today == pytest.approx(6.15, rel=1e-3)
        a_today = float(hass.states.get("sensor.zuhause_string_a_energy_today").state)
        assert a_today == pytest.approx(2.4, rel=1e-3)

        # Outage: energy sensors stay available, live sensors go unavailable
        pw.strings.return_value = {}
        freezer.tick(timedelta(seconds=10))
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get("sensor.zuhause_pv_power").state == "unavailable"
        assert float(hass.states.get("sensor.zuhause_pv_energy_today").state) == pytest.approx(today, rel=1e-3)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_energy_survives_reload(hass: HomeAssistant, freezer) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DIN,
        data={CONF_CONNECTION_TYPE: CONNECTION_WIFI, CONF_HOST: "192.168.91.1",
              CONF_GW_PASSWORD: "ABCDEFGHIJ", CONF_RSA_KEY_PATH: ""},
    )
    entry.add_to_hass(hass)
    freezer.move_to("2026-10-22T10:00:00+00:00")
    pw = make_pw()
    with patch("custom_components.powerwall3_local.api.pypowerwall.Powerwall", return_value=pw):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        for _ in range(6):
            freezer.tick(timedelta(seconds=10))
            await entry.runtime_data.async_refresh()
        before = entry.runtime_data.energy["total"].total_kwh
        assert before > 0

        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        after = float(hass.states.get("sensor.zuhause_pv_energy_total").state)
        assert after == pytest.approx(before, rel=1e-3)
        assert await hass.config_entries.async_unload(entry.entry_id)
