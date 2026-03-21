"""Base entity for WaterGenius integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import WaterGeniusCoordinator


class WaterGeniusEntity(CoordinatorEntity[WaterGeniusCoordinator]):
    """Base class for WaterGenius entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WaterGeniusCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.address)},
            name=self.coordinator.device_name,
            manufacturer=MANUFACTURER,
            model="Water Softener",
        )
