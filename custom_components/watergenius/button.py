"""Button entities for WaterGenius integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WaterGeniusCoordinator
from .entity import WaterGeniusEntity


@dataclass(frozen=True, kw_only=True)
class WaterGeniusButtonDescription(ButtonEntityDescription):
    """Describe a WaterGenius button."""

    command_value: int


BUTTON_DESCRIPTIONS: tuple[WaterGeniusButtonDescription, ...] = (
    WaterGeniusButtonDescription(
        key="regen_immediate",
        name="Immediate Proportional Regeneration",
        icon="mdi:recycle",
        command_value=1,
    ),
    WaterGeniusButtonDescription(
        key="regen_tonight",
        name="Full Regeneration Tonight",
        icon="mdi:recycle-variant",
        command_value=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WaterGenius buttons."""
    coordinator: WaterGeniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WaterGeniusButton(coordinator, desc) for desc in BUTTON_DESCRIPTIONS
    )


class WaterGeniusButton(WaterGeniusEntity, ButtonEntity):
    """A WaterGenius button entity."""

    entity_description: WaterGeniusButtonDescription

    def __init__(
        self,
        coordinator: WaterGeniusCoordinator,
        description: WaterGeniusButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_send_command(
            "f_ucRegenDelay", self.entity_description.command_value
        )
