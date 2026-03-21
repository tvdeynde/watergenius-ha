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
from .gizwits_protocol import WaterGeniusDeviceData

_LOGGER = logging.getLogger(__name__)


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
        self._got_data = False

        # Set up data callback
        self._ble.set_status_callback(self._handle_data_dump)

    @property
    def address(self) -> str:
        """Return the BLE device address."""
        return self._device.address

    @property
    def device_name(self) -> str:
        """Return the device name."""
        return self._device_name

    def _handle_data_dump(self, data: bytes) -> None:
        """Handle incoming data dump from the device.

        The device sends its complete state as a raw binary dump.
        We need to find the data point values within this dump.

        The exact byte offsets need to be determined by comparing
        known values from the phone app with the binary data.
        For now, we log the data for analysis and attempt parsing.
        """
        _LOGGER.info("Received data dump (%d bytes)", len(data))

        # Try to parse the data dump
        self._parse_data_dump(data)
        self._got_data = True

        # Schedule HA state update
        self.async_set_updated_data(self._data)

    def _parse_data_dump(self, data: bytes) -> None:
        """Parse the raw binary data dump from the device.

        The device sends ~900+ bytes containing configuration, status,
        and historical data. The format is proprietary.

        Based on log analysis, the dump contains:
        - Device config (serial, product key, email)
        - Current sensor values
        - Historical usage data
        - Regeneration schedules

        The exact byte mapping is determined by analyzing dumps with
        known values from the phone app. This parser will be refined
        as we identify more data points.

        For now, we attempt to find known patterns and extract values.
        """
        if len(data) < 200:
            _LOGGER.debug("Data dump too short (%d bytes), skipping", len(data))
            return

        # Log key sections of the dump for analysis
        # The data appears to have this rough structure:
        # Bytes 0-9: Header/version info
        # Bytes 10-37: 0xFF padding
        # Bytes 38+: Config data (serial, product key in ASCII)
        # After product key: Sensor values
        # Later: Historical data, schedules

        # Find the product key to anchor our position
        # Product key is stored as ASCII hex in the dump
        pk_ascii = b"1952e24e"
        pk_pos = data.find(pk_ascii)

        if pk_pos < 0:
            # Try the other product key
            pk_ascii = b"1462685633a0"
            pk_pos = data.find(pk_ascii)

        if pk_pos >= 0:
            _LOGGER.info("Found product key at byte offset %d", pk_pos)
            # The product key is 32 ASCII hex chars = 64 bytes
            # Data points follow after the product key + some padding
            after_pk = pk_pos + 64

            if after_pk + 100 <= len(data):
                sensor_area = data[after_pk:]
                _LOGGER.info(
                    "Sensor area (from offset %d, %d bytes): %s",
                    after_pk,
                    len(sensor_area),
                    sensor_area[:200].hex(),
                )
                self._try_parse_sensor_area(sensor_area)
        else:
            _LOGGER.warning("Could not find product key anchor in data dump")
            # Try parsing from the start with best-effort offsets
            self._try_parse_sensor_area(data)

    def _try_parse_sensor_area(self, data: bytes) -> None:
        """Attempt to extract sensor values from the data area.

        This is a best-effort parser that will be refined based on
        comparing values with the phone app. Values are logged for
        debugging.

        Based on analysis of the data dump, after the product key
        there's a section with 2-byte and 4-byte big-endian values
        that likely correspond to sensor readings.
        """
        if len(data) < 50:
            return

        # Log candidate values at various offsets for manual correlation
        # with the phone app
        _LOGGER.info("=== Candidate sensor values (2-byte BE) ===")
        for i in range(0, min(len(data) - 1, 100), 2):
            val = int.from_bytes(data[i : i + 2], "big")
            if 0 < val < 10000:  # Filter out obviously wrong values
                _LOGGER.info("  offset %3d: %5d (0x%04X)", i, val, val)

        _LOGGER.info("=== Candidate sensor values (4-byte BE) ===")
        for i in range(0, min(len(data) - 3, 100), 4):
            val = int.from_bytes(data[i : i + 4], "big")
            if 0 < val < 1000000:
                _LOGGER.info("  offset %3d: %7d (0x%08X)", i, val, val)

    async def _async_update_data(self) -> WaterGeniusDeviceData | None:
        """Fetch data from the device via BLE."""
        # Ensure connection
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
            # Request fresh data from device
            await self._ble.request_status()
            # Wait for the device to send its data dump via notifications
            await asyncio.sleep(3)
        except Exception as err:
            _LOGGER.warning("Error requesting status: %s", err)
            await self._ble.disconnect()
            raise UpdateFailed(
                f"Error communicating with device: {err}"
            ) from err

        return self._data

    async def async_send_command(self, dp_name: str, value: int) -> None:
        """Send a control command to the device.

        TODO: The exact command format for this device's proprietary
        protocol needs to be reverse-engineered from the phone app's
        BLE communication.
        """
        _LOGGER.warning(
            "Control commands not yet implemented for this device protocol"
        )

    async def async_shutdown(self) -> None:
        """Disconnect from the device on shutdown."""
        await self._ble.disconnect()
