"""WaterGenius Water Softener integration for Home Assistant.

Connects to WaterGenius water softener devices via Bluetooth using
the Gizwits GAgent BLE protocol to read sensor data and provide controls.
"""

from __future__ import annotations

import logging

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_DEVICE_ADDRESS, DOMAIN
from .coordinator import WaterGeniusCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WaterGenius from a config entry."""
    address = entry.data[CONF_DEVICE_ADDRESS]

    # Get the BLE device from HA's Bluetooth integration
    device = async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        raise ConfigEntryNotReady(
            f"WaterGenius device {address} not found. Is it powered on and in range?"
        )

    device_name = entry.title or "WaterGenius"

    coordinator = WaterGeniusCoordinator(
        hass,
        device=device,
        device_name=device_name,
    )

    # Perform initial data fetch
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: WaterGeniusCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
