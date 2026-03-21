"""Binary sensor entities for WaterGenius integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WaterGeniusCoordinator
from .entity import WaterGeniusEntity
from .gizwits_protocol import WaterGeniusDeviceData


@dataclass(frozen=True, kw_only=True)
class WaterGeniusBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a WaterGenius binary sensor."""

    value_fn: Callable[[WaterGeniusDeviceData], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[WaterGeniusBinarySensorDescription, ...] = (
    WaterGeniusBinarySensorDescription(
        key="alarm_active",
        name="Alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert",
        value_fn=lambda data: data.alarm_active,
    ),
    WaterGeniusBinarySensorDescription(
        key="regenerating",
        name="Regenerating",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:recycle",
        value_fn=lambda data: data.is_regenerating,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterGenius binary sensors."""
    coordinator: WaterGeniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WaterGeniusBinarySensor(coordinator, desc)
        for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class WaterGeniusBinarySensor(WaterGeniusEntity, BinarySensorEntity):
    """A WaterGenius binary sensor entity."""

    entity_description: WaterGeniusBinarySensorDescription

    def __init__(
        self,
        coordinator: WaterGeniusCoordinator,
        description: WaterGeniusBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
