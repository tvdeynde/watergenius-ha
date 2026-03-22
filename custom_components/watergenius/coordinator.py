"""DataUpdateCoordinator for WaterGenius integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak.backends.device import BLEDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .gizwits_ble import GizwitsBleConnection
from .gizwits_protocol import WaterGeniusDeviceData, bytes2number

_LOGGER = logging.getLogger(__name__)

# BLE data = 38-byte header + 807-byte Gizwits payload
# Header offset verified by matching product key and hardness values
_HEADER_SIZE = 38

# The device sends a full data dump ~8s after connecting.
_INITIAL_WAIT = 12
_POLL_WAIT = 5

# Data point layout from Gizwits API schema (product_key 1952e24ea3744832aa55cf9a5050fc6d)
# Each entry: (payload_offset, length, name, description)
# Payload offset = position within the 807-byte Gizwits payload
# BLE offset = payload_offset + _HEADER_SIZE
_DATA_POINTS = [
    (0, 1, "valve_type", "Valve type"),
    (248, 1, "hardness_unit", "Hardness unit setting"),
    (249, 2, "incoming_hardness", "Incoming water hardness"),
    (251, 2, "outgoing_hardness", "Outgoing water hardness"),
    (254, 1, "salt_setting", "Salt amount setting"),
    (257, 2, "regen_time", "Regeneration time (hour*256+min)"),
    (425, 2, "flow_current", "Current flow rate"),
    (427, 4, "total_capacity", "Total capacity (L)"),
    (431, 4, "remaining_capacity_l", "Remaining capacity (L)"),
    (435, 2, "fill_time", "Refill time"),
    (437, 2, "regen_times_total", "Total regeneration count"),
    (441, 1, "next_regen_days", "Days to next regeneration"),
    (442, 4, "last_regen_time", "Last regeneration time"),
    (446, 4, "last2_regen_time", "2nd last regeneration time"),
    (450, 2, "peak_flow", "Peak flow rate"),
    (452, 4, "last_hour_vol", "Last hour volume"),
    (456, 4, "today_vol", "Today volume"),
    (460, 4, "total_vol", "Total volume used"),
    (465, 2, "vacation_status", "Vacation mode status"),
    (467, 4, "avg_daily_vol", "Average daily volume"),
    (471, 1, "regen_enabled", "Regeneration enabled"),
    (472, 4, "regen_status", "Regeneration status"),
    (476, 6, "error_log", "Current error"),
    (482, 1, "leak_count_24h", "Leak count in 24 hours"),
    (500, 1, "salt_level", "Current salt level"),
    (501, 4, "total_caco3", "Total CaCO3 removed (g)"),
    (714, 4, "daily_water_usage_avg", "Average daily water usage"),
    (794, 2, "est_days_to_next", "Estimated days to next regen"),
    (796, 1, "week_regen_flag", "Weekly regeneration flags"),
]


class WaterGeniusCoordinator(DataUpdateCoordinator[WaterGeniusDeviceData | None]):
    """Coordinator for polling WaterGenius device data over BLE."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: BLEDevice,
        device_name: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device.address}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._device = device
        self._device_name = device_name
        self._ble = GizwitsBleConnection(device)
        self._data = WaterGeniusDeviceData()
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._first_fetch = True

        self._ble.set_status_callback(self._handle_data_dump)

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def device_name(self) -> str:
        return self._device_name

    def _handle_data_dump(self, data: bytes) -> None:
        """Handle incoming data dump from the device."""
        _LOGGER.info("Received data dump (%d bytes)", len(data))
        self._parse_data_dump(data)
        self.async_set_updated_data(self._data)

    def _parse_data_dump(self, data: bytes) -> None:
        """Parse the raw binary data dump.

        The BLE data consists of a 38-byte header followed by the
        807-byte Gizwits product payload. Data point positions are
        defined by the official Gizwits product schema.

        The device also sends shorter periodic updates (~42 bytes)
        which contain a subset of status data.
        """
        if len(data) >= _HEADER_SIZE + 500:
            self._parse_full_dump(data)
        elif len(data) >= 40:
            self._parse_periodic_update(data)
        else:
            _LOGGER.debug("Data too short to parse (%d bytes)", len(data))

    def _parse_full_dump(self, data: bytes) -> None:
        """Parse the full data dump using Gizwits schema offsets."""
        _LOGGER.info("Parsing full data dump (%d bytes)", len(data))

        payload_size = len(data) - _HEADER_SIZE
        _LOGGER.debug("Payload size: %d bytes (expected ~807)", payload_size)

        for p_offset, length, name, desc in _DATA_POINTS:
            ble_offset = p_offset + _HEADER_SIZE
            if ble_offset + length <= len(data):
                raw = data[ble_offset : ble_offset + length]
                self._data.raw[name] = raw
                val = bytes2number(raw)
                _LOGGER.info("  %s = %d (offset %d, %d bytes)", name, val, p_offset, length)
            else:
                _LOGGER.debug("  %s: offset %d out of range", name, p_offset)

        # Also extract remaining capacity percentage
        # This isn't a standard Gizwits data point but can be calculated
        total = self._data.total_capacity
        remain = self._data.remaining_capacity
        if total and remain and total > 0:
            pct = int(remain * 100 / total)
            self._data.raw["remaining_capacity_pct"] = bytes([min(pct, 100)])
            _LOGGER.info("  remaining_capacity_pct = %d%% (calculated)", pct)

    def _parse_periodic_update(self, data: bytes) -> None:
        """Parse the periodic status update (~42 bytes).

        These short updates contain a condensed status. The exact
        mapping is still being refined, but we can extract the
        remaining capacity percentage from position 35.
        """
        _LOGGER.info("Parsing periodic update (%d bytes): %s", len(data), data.hex())

        # The periodic update appears to contain a subset of values
        # For now, log the raw data for further analysis
        if len(data) > 8:
            _LOGGER.info("  Periodic header bytes: %s", data[:10].hex())
        if len(data) > 35:
            _LOGGER.info("  Periodic tail bytes: %s", data[30:].hex())

    async def _async_update_data(self) -> WaterGeniusDeviceData | None:
        """Fetch data from the device via BLE."""
        if not self._ble.is_connected:
            if self._reconnect_attempts >= self._max_reconnect_attempts:
                raise UpdateFailed(
                    f"Failed to connect after {self._max_reconnect_attempts} attempts"
                )
            self._reconnect_attempts += 1
            _LOGGER.info(
                "Connecting to WaterGenius device (attempt %d/%d)",
                self._reconnect_attempts,
                self._max_reconnect_attempts,
            )
            connected = await self._ble.connect()
            if not connected:
                raise UpdateFailed("Failed to connect to WaterGenius device")
            self._reconnect_attempts = 0

        try:
            await self._ble.request_status()
            wait = _INITIAL_WAIT if self._first_fetch else _POLL_WAIT
            self._first_fetch = False
            _LOGGER.debug("Waiting %d seconds for device response", wait)
            await asyncio.sleep(wait)
        except Exception as err:
            _LOGGER.warning("Error requesting status: %s", err)
            await self._ble.disconnect()
            raise UpdateFailed(
                f"Error communicating with device: {err}"
            ) from err

        return self._data

    async def async_send_command(self, dp_name: str, value: int) -> None:
        """Send a control command to the device."""
        _LOGGER.warning(
            "Control commands not yet implemented for this device protocol"
        )

    async def async_shutdown(self) -> None:
        """Disconnect from the device on shutdown."""
        await self._ble.disconnect()
