"""Diagnostics support for WaterGenius integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WaterGeniusCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Includes the raw BLE data dump so data point offsets can be
    verified against values shown in the vendor app.
    """
    coordinator: WaterGeniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data

    return {
        "device_name": coordinator.device_name,
        "raw_fields": (
            {name: value.hex() for name, value in data.raw.items()}
            if data is not None
            else None
        ),
        "last_full_dump_hex": (
            coordinator.last_dump.hex() if coordinator.last_dump else None
        ),
        "last_full_dump_size": (
            len(coordinator.last_dump) if coordinator.last_dump else 0
        ),
    }
