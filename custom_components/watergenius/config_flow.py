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
from homeassistant.const import CONF_ADDRESS

from .const import (
    CONF_DEVICE_ADDRESS,
    CONF_MESH_NAME,
    CONF_MESH_PASSWORD,
    DEFAULT_MESH_NAME,
    DEFAULT_MESH_PASSWORD,
    DOMAIN,
    SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)

# Known device name patterns for WaterGenius / Gizwits Telink mesh devices
_KNOWN_NAME_PREFIXES = (
    "watergenius",
    "water genius",
    "telink",
    "gizwits",
    "xb_",
    "mesh",
    "out_of_mesh",
)

# Manual entry sentinel
_MANUAL_ENTRY = "__manual__"


def _is_potential_watergenius(info: BluetoothServiceInfoBleak) -> bool:
    """Check if a discovered BLE device could be a WaterGenius device.

    Matches on:
    1. Service UUID (if the device advertises it)
    2. Device name containing known prefixes
    3. Any device advertising the Telink mesh service UUID
    """
    # Check service UUIDs
    if SERVICE_UUID.lower() in [s.lower() for s in info.service_uuids]:
        return True

    # Check device name
    name = (info.name or "").lower().strip()
    if name:
        for prefix in _KNOWN_NAME_PREFIXES:
            if prefix in name:
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
            return await self.async_step_mesh_credentials()

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
            # Basic MAC address validation
            if len(address.replace(":", "").replace("-", "")) != 12:
                errors[CONF_DEVICE_ADDRESS] = "invalid_address"
            else:
                # Normalize to colon-separated format
                raw = address.replace(":", "").replace("-", "")
                self._selected_address = ":".join(
                    raw[i : i + 2] for i in range(0, 12, 2)
                )
                return await self.async_step_mesh_credentials()

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
        _LOGGER.debug("Discovered WaterGenius device: %s", discovery_info.address)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._selected_address = discovery_info.address
        self._discovered_devices[discovery_info.address] = discovery_info

        return await self.async_step_mesh_credentials()

    async def async_step_mesh_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle mesh credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mesh_name = user_input.get(CONF_MESH_NAME, DEFAULT_MESH_NAME)
            mesh_password = user_input.get(CONF_MESH_PASSWORD, DEFAULT_MESH_PASSWORD)

            address = self._selected_address
            if not address:
                return self.async_abort(reason="no_devices_found")

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            # Determine device name from discovery info
            info = self._discovered_devices.get(address)
            device_name = (info.name if info else None) or "WaterGenius"

            return self.async_create_entry(
                title=device_name,
                data={
                    CONF_DEVICE_ADDRESS: address,
                    CONF_MESH_NAME: mesh_name,
                    CONF_MESH_PASSWORD: mesh_password,
                },
            )

        return self.async_show_form(
            step_id="mesh_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MESH_NAME, default=DEFAULT_MESH_NAME): str,
                    vol.Required(
                        CONF_MESH_PASSWORD, default=DEFAULT_MESH_PASSWORD
                    ): str,
                }
            ),
            errors=errors,
        )
