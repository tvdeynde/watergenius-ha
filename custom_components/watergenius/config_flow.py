"""Config flow for WaterGenius integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_DEVICE_ADDRESS,
    DOMAIN,
    GIZWITS_MANUFACTURER_ID,
    PRODUCT_KEYS,
    SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)

# Manual entry sentinel
_MANUAL_ENTRY = "__manual__"


def _is_potential_watergenius(info: BluetoothServiceInfoBleak) -> bool:
    """Check if a discovered BLE device could be a WaterGenius device.

    Matches on:
    1. Gizwits BLE service UUID (0xABF0)
    2. Device name starting with "XPG-GAgent" (Gizwits GAgent device)
    3. Gizwits manufacturer ID (0x1910) with known product key in data
    """
    # Check service UUID
    if SERVICE_UUID.lower() in [s.lower() for s in info.service_uuids]:
        return True

    # Check device name
    name = (info.name or "").lower().strip()
    if name.startswith("xpg-gagent"):
        return True

    # Check manufacturer data for Gizwits ID with known product key
    if hasattr(info, "manufacturer_data"):
        mfr_data = info.manufacturer_data.get(GIZWITS_MANUFACTURER_ID)
        if mfr_data:
            # Manufacturer data contains the product key
            data_hex = bytes(mfr_data).hex()
            for pk in PRODUCT_KEYS:
                if pk in data_hex:
                    return True

    return False


class WaterGeniusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WaterGenius."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._selected_address: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: discover and select a device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input[CONF_DEVICE_ADDRESS]
            if selected == _MANUAL_ENTRY:
                return await self.async_step_manual()
            self._selected_address = selected
            return await self._create_entry()

        # Discover potential WaterGenius BLE devices
        self._discovered_devices = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            if _is_potential_watergenius(info):
                self._discovered_devices[info.address] = info

        # Build selection list — always include manual entry option
        device_options = {
            addr: f"{info.name or 'Unknown'} ({addr})"
            for addr, info in self._discovered_devices.items()
        }
        device_options[_MANUAL_ENTRY] = "Enter address manually..."

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ADDRESS): vol.In(device_options),
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual BLE address entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_DEVICE_ADDRESS].strip().upper()
            raw = address.replace(":", "").replace("-", "")
            if len(raw) != 12:
                errors[CONF_DEVICE_ADDRESS] = "invalid_address"
            else:
                self._selected_address = ":".join(
                    raw[i : i + 2] for i in range(0, 12, 2)
                )
                return await self._create_entry()

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ADDRESS): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "example": "AA:BB:CC:DD:EE:FF",
            },
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery."""
        _LOGGER.debug(
            "Discovered WaterGenius device: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._selected_address = discovery_info.address
        self._discovered_devices[discovery_info.address] = discovery_info

        return await self._create_entry()

    async def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry for the selected device."""
        address = self._selected_address
        if not address:
            return self.async_abort(reason="no_devices_found")

        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        info = self._discovered_devices.get(address)
        device_name = (info.name if info else None) or "WaterGenius"

        return self.async_create_entry(
            title=device_name,
            data={
                CONF_DEVICE_ADDRESS: address,
            },
        )
