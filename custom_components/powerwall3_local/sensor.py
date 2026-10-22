"""Sensors for Powerwall 3 Local."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PowerwallData, StringData
from .const import CONF_GROUPS, DOMAIN, MANUFACTURER, MODEL, TOTAL_KEY
from .coordinator import Powerwall3ConfigEntry, Powerwall3Coordinator


# --- descriptions ----------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class StringSensorDescription(SensorEntityDescription):
    """Per-string sensor."""

    value_fn: Callable[[StringData], float | str | None]


@dataclass(frozen=True, kw_only=True)
class SiteSensorDescription(SensorEntityDescription):
    """Site-level sensor."""

    value_fn: Callable[[PowerwallData], float | str | None]


STRING_SENSORS: tuple[StringSensorDescription, ...] = (
    StringSensorDescription(
        key="power",
        translation_key="string_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda s: s.power,
    ),
    StringSensorDescription(
        key="voltage",
        translation_key="string_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda s: s.voltage,
    ),
    StringSensorDescription(
        key="current",
        translation_key="string_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=lambda s: s.current,
    ),
    StringSensorDescription(
        key="state",
        translation_key="string_state",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.state,
    ),
)

SITE_SENSORS: tuple[SiteSensorDescription, ...] = (
    SiteSensorDescription(
        key="pv_power",
        translation_key="pv_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.pv_power,
    ),
    SiteSensorDescription(
        key="site_solar_power",
        translation_key="site_solar_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.site_solar_power,
    ),
    SiteSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda d: d.battery_level,
    ),
    SiteSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.battery_power,
    ),
    SiteSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.grid_power,
    ),
    SiteSensorDescription(
        key="load_power",
        translation_key="load_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.load_power,
    ),
    SiteSensorDescription(
        key="grid_status",
        translation_key="grid_status",
        value_fn=lambda d: d.grid_status,
    ),
)

ENERGY_TODAY = SensorEntityDescription(
    key="energy_today",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    suggested_display_precision=2,
)
ENERGY_TOTAL = SensorEntityDescription(
    key="energy_total",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    suggested_display_precision=2,
)


# --- setup -------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Powerwall3ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create entities for every PV string seen in the first poll."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for string_name in coordinator.data.strings:
        entities.extend(
            StringSensor(coordinator, string_name, desc) for desc in STRING_SENSORS
        )
        entities.append(EnergySensor(coordinator, string_name, today=True))
        entities.append(EnergySensor(coordinator, string_name, today=False))

    entities.extend(SiteSensor(coordinator, desc) for desc in SITE_SENSORS)
    entities.append(EnergySensor(coordinator, TOTAL_KEY, today=True))
    entities.append(EnergySensor(coordinator, TOTAL_KEY, today=False))

    groups: list[dict] = entry.options.get(CONF_GROUPS, [])
    for group in groups:
        entities.extend(GroupSensor(coordinator, group, desc) for desc in GROUP_SENSORS)
        entities.append(GroupEnergySensor(coordinator, group, today=True))
        entities.append(GroupEnergySensor(coordinator, group, today=False))

    _remove_stale_group_entities(hass, entry, coordinator.info.din, {g["id"] for g in groups})
    async_add_entities(entities)


def _remove_stale_group_entities(
    hass: HomeAssistant, entry: Powerwall3ConfigEntry, din: str, group_ids: set[str]
) -> None:
    """Delete entities of groups that were removed in the options."""
    registry = er.async_get(hass)
    prefix = f"{din}_group_"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.startswith(prefix):
            group_id = entity.unique_id[len(prefix):].split("_", 1)[0]
            if group_id not in group_ids:
                registry.async_remove(entity.entity_id)


# --- group helpers -------------------------------------------------------------


def _group_power(data: PowerwallData, members: list[str]) -> float | None:
    values = [data.strings[s].power for s in members if s in data.strings]
    values = [max(v, 0.0) for v in values if v is not None]
    return float(sum(values)) if values else None


def _group_current(data: PowerwallData, members: list[str]) -> float | None:
    values = [data.strings[s].current for s in members if s in data.strings]
    values = [v for v in values if v is not None]
    return float(sum(values)) if values else None


def _group_voltage(data: PowerwallData, members: list[str]) -> float | None:
    """Average of the members that carry voltage (parallel strings share one)."""
    values = [data.strings[s].voltage for s in members if s in data.strings]
    values = [v for v in values if v is not None and v > 0]
    return float(sum(values) / len(values)) if values else (0.0 if members else None)


@dataclass(frozen=True, kw_only=True)
class GroupSensorDescription(SensorEntityDescription):
    """Sensor over a group of strings."""

    value_fn: Callable[[PowerwallData, list[str]], float | None]


GROUP_SENSORS: tuple[GroupSensorDescription, ...] = (
    GroupSensorDescription(
        key="power",
        translation_key="group_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_group_power,
    ),
    GroupSensorDescription(
        key="voltage",
        translation_key="group_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=_group_voltage,
    ),
    GroupSensorDescription(
        key="current",
        translation_key="group_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=_group_current,
    ),
)


# --- entities ----------------------------------------------------------------


class Powerwall3Entity(CoordinatorEntity[Powerwall3Coordinator]):
    """Common base: device info and unique id prefix."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Powerwall3Coordinator) -> None:
        super().__init__(coordinator)
        info = coordinator.info
        self._din = info.din
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.din)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=info.site_name or MODEL,
            serial_number=info.din,
            sw_version=info.version,
        )


class StringSensor(Powerwall3Entity, SensorEntity):
    """Live value of one PV string."""

    entity_description: StringSensorDescription

    def __init__(
        self,
        coordinator: Powerwall3Coordinator,
        string_name: str,
        description: StringSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._string = string_name
        self._attr_unique_id = f"{self._din}_string_{string_name}_{description.key}"
        self._attr_translation_placeholders = {"string": string_name}

    @property
    def available(self) -> bool:
        return super().available and self._string in self.coordinator.data.strings

    @property
    def native_value(self) -> float | str | None:
        string = self.coordinator.data.strings.get(self._string)
        return None if string is None else self.entity_description.value_fn(string)


class SiteSensor(Powerwall3Entity, SensorEntity):
    """Site-level value (battery, grid, load, PV sum)."""

    entity_description: SiteSensorDescription

    def __init__(
        self, coordinator: Powerwall3Coordinator, description: SiteSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._din}_{description.key}"

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self.coordinator.data)


class EnergySensor(Powerwall3Entity, SensorEntity):
    """Integrated energy of one string (or the sum), today or lifetime.

    Stays available while the Powerwall is unreachable so that the daily
    value does not flap to 'unavailable' (and confuse PVOutput uploads).
    """

    def __init__(self, coordinator: Powerwall3Coordinator, key: str, today: bool) -> None:
        super().__init__(coordinator)
        self._key = key
        self._today = today
        self.entity_description = ENERGY_TODAY if today else ENERGY_TOTAL
        suffix = "today" if today else "total"
        if key == TOTAL_KEY:
            self._attr_unique_id = f"{self._din}_pv_energy_{suffix}"
            self._attr_translation_key = f"pv_energy_{suffix}"
        else:
            self._attr_unique_id = f"{self._din}_string_{key}_energy_{suffix}"
            self._attr_translation_key = f"string_energy_{suffix}"
            self._attr_translation_placeholders = {"string": key}

    @property
    def available(self) -> bool:
        return self._key in self.coordinator.energy

    @property
    def native_value(self) -> float | None:
        acc = self.coordinator.energy.get(self._key)
        if acc is None:
            return None
        return round(acc.today_kwh if self._today else acc.total_kwh, 4)


class GroupSensor(Powerwall3Entity, SensorEntity):
    """Live value (power, voltage, current) of a string group."""

    entity_description: GroupSensorDescription

    def __init__(
        self,
        coordinator: Powerwall3Coordinator,
        group: dict,
        description: GroupSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._members: list[str] = list(group["strings"])
        self._attr_unique_id = f"{self._din}_group_{group['id']}_{description.key}"
        self._attr_translation_placeholders = {"group": group["name"]}
        self._attr_extra_state_attributes = {"strings": self._members}

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data, self._members)


class GroupEnergySensor(Powerwall3Entity, SensorEntity):
    """Energy of a group = sum of its strings' energy counters.

    Because it sums the per-string counters, the group includes everything
    the strings produced today, even before the group was created.
    """

    def __init__(self, coordinator: Powerwall3Coordinator, group: dict, today: bool) -> None:
        super().__init__(coordinator)
        self._members: list[str] = list(group["strings"])
        self._today = today
        self.entity_description = ENERGY_TODAY if today else ENERGY_TOTAL
        suffix = "today" if today else "total"
        self._attr_unique_id = f"{self._din}_group_{group['id']}_energy_{suffix}"
        self._attr_translation_key = f"group_energy_{suffix}"
        self._attr_translation_placeholders = {"group": group["name"]}
        self._attr_extra_state_attributes = {"strings": self._members}

    @property
    def available(self) -> bool:
        return any(s in self.coordinator.energy for s in self._members)

    @property
    def native_value(self) -> float | None:
        accs = [self.coordinator.energy[s] for s in self._members if s in self.coordinator.energy]
        if not accs:
            return None
        total = sum(a.today_kwh if self._today else a.total_kwh for a in accs)
        return round(total, 4)
