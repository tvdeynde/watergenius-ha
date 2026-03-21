"""Switch entities for WaterGenius integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WaterGeniusCoordinator
from .entity import WaterGeniusEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterGenius switches."""
    coordinator: WaterGeniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SaltAlarmSoundSwitch(coordinator)])


class SaltAlarmSoundSwitch(WaterGeniusEntity, SwitchEntity):
    """Switch to control the salt alarm sound."""

    _attr_name = "Salt Alarm Sound"
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator: WaterGeniusCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "salt_alarm_sound")

    @property
    def is_on(self) -> bool | None:
        """Return true if the salt alarm sound is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get_bool("f_ucTipsSoundSet")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the salt alarm sound."""
        await self.coordinator.async_send_command("f_ucTipsSoundSet", 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the salt alarm sound."""
        await self.coordinator.async_send_command("f_ucTipsSoundSet", 0)
