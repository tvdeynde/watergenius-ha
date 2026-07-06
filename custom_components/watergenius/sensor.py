"""Sensor entities for WaterGenius integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, HARDNESS_UNITS, VALVE_STATES
from .coordinator import WaterGeniusCoordinator
from .entity import WaterGeniusEntity
from .gizwits_protocol import WaterGeniusDeviceData


@dataclass(frozen=True, kw_only=True)
class WaterGeniusSensorDescription(SensorEntityDescription):
    """Describe a WaterGenius sensor."""

    value_fn: Callable[[WaterGeniusDeviceData], int | float | str | None]
    extra_attrs_fn: Callable[[WaterGeniusDeviceData], dict | None] | None = None


def _hardness_unit(data: WaterGeniusDeviceData) -> str | None:
    idx = data.hardness_unit_index
    if idx is None:
        return None
    return HARDNESS_UNITS.get(idx, "mg/L")


def _valve_state_str(data: WaterGeniusDeviceData) -> str | None:
    vs = data.valve_state
    if vs is None:
        return None
    return VALVE_STATES.get(vs, f"Unknown ({vs})")


def _regen_countdown_str(data: WaterGeniusDeviceData) -> int | None:
    val = data.regen_countdown
    if val is None:
        return None
    # Value encodes minutes and seconds
    minutes = val // 60
    seconds = val % 60
    return minutes * 60 + seconds


def _regen_time_str(data: WaterGeniusDeviceData) -> str | None:
    # Minutes since midnight (the app stores it as hour*60+minute)
    val = data.get_number("regen_time")
    if val is None:
        return None
    hours = val // 60
    minutes = val % 60
    return f"{hours:02d}:{minutes:02d}"


SENSOR_DESCRIPTIONS: tuple[WaterGeniusSensorDescription, ...] = (
    WaterGeniusSensorDescription(
        key="water_hardness_in",
        translation_key="water_hardness_in",
        name="Incoming Hardness",
        icon="mdi:water-opacity",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.incoming_hardness,
    ),
    WaterGeniusSensorDescription(
        key="water_hardness_out",
        translation_key="water_hardness_out",
        name="Outgoing Hardness",
        icon="mdi:water-opacity",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.outgoing_hardness,
    ),
    WaterGeniusSensorDescription(
        key="hardness_unit",
        translation_key="hardness_unit",
        name="Hardness Unit",
        icon="mdi:ruler",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_hardness_unit,
    ),
    WaterGeniusSensorDescription(
        key="flow_rate",
        translation_key="flow_rate",
        name="Current Flow Rate",
        icon="mdi:water-pump",
        native_unit_of_measurement="L/min",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.flow_current,
    ),
    WaterGeniusSensorDescription(
        key="remaining_capacity",
        translation_key="remaining_capacity",
        name="Remaining Capacity",
        icon="mdi:water-percent",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.remaining_capacity,
    ),
    WaterGeniusSensorDescription(
        key="remaining_capacity_pct",
        translation_key="remaining_capacity_pct",
        name="Remaining Capacity %",
        icon="mdi:water-percent",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.remaining_capacity_pct,
    ),
    WaterGeniusSensorDescription(
        key="total_capacity",
        translation_key="total_capacity",
        name="Total Capacity",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.total_capacity,
    ),
    WaterGeniusSensorDescription(
        key="days_to_next_regen",
        translation_key="days_to_next_regen",
        name="Days to Next Regeneration",
        icon="mdi:calendar-clock",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda data: data.days_to_next_regen,
    ),
    WaterGeniusSensorDescription(
        key="daily_water_usage_avg",
        translation_key="daily_water_usage_avg",
        name="Average Daily Water Usage",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.daily_water_usage_avg,
    ),
    WaterGeniusSensorDescription(
        key="total_hardness_removal",
        translation_key="total_hardness_removal",
        name="Total Hardness Removal",
        icon="mdi:water-minus",
        native_unit_of_measurement="mg CaCO₃",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.total_hardness_removal,
    ),
    WaterGeniusSensorDescription(
        key="valve_state",
        translation_key="valve_state",
        name="Valve State",
        icon="mdi:valve",
        value_fn=_valve_state_str,
    ),
    WaterGeniusSensorDescription(
        key="regen_countdown",
        translation_key="regen_countdown",
        name="Regeneration Countdown",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_regen_countdown_str,
    ),
    WaterGeniusSensorDescription(
        key="regen_time",
        translation_key="regen_time",
        name="Regeneration Time",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_regen_time_str,
    ),
    WaterGeniusSensorDescription(
        key="daily_water_usage_detail",
        translation_key="daily_water_usage_detail",
        name="Daily Water Usage Detail",
        icon="mdi:chart-bar",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.daily_water_usage_avg,
        extra_attrs_fn=lambda data: {
            "usage_2h_slots": data.daily_usage_2h,
            "weekly_flow_avg": data.weekly_flow_avg,
            "monthly_flow_avg": data.monthly_flow_avg,
            "weekly_water_usage": data.weekly_water_usage,
        },
    ),
    WaterGeniusSensorDescription(
        key="error_log",
        translation_key="error_log",
        name="Error Log",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.error_log,
    ),
    WaterGeniusSensorDescription(
        key="today_volume",
        translation_key="today_volume",
        name="Today Water Usage",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.today_vol,
    ),
    WaterGeniusSensorDescription(
        key="total_volume",
        translation_key="total_volume",
        name="Total Water Usage",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.total_vol,
    ),
    WaterGeniusSensorDescription(
        key="peak_flow",
        translation_key="peak_flow",
        name="Peak Flow Rate",
        icon="mdi:speedometer",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.peak_flow,
    ),
    WaterGeniusSensorDescription(
        key="regen_count",
        translation_key="regen_count",
        name="Total Regeneration Count",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.regen_times_total,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterGenius sensors."""
    coordinator: WaterGeniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WaterGeniusSensor(coordinator, desc) for desc in SENSOR_DESCRIPTIONS
    )


class WaterGeniusSensor(WaterGeniusEntity, SensorEntity):
    """A WaterGenius sensor entity."""

    entity_description: WaterGeniusSensorDescription

    def __init__(
        self,
        coordinator: WaterGeniusCoordinator,
        description: WaterGeniusSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | float | str | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return extra state attributes."""
        if (
            self.entity_description.extra_attrs_fn is None
            or self.coordinator.data is None
        ):
            return None
        return self.entity_description.extra_attrs_fn(self.coordinator.data)
