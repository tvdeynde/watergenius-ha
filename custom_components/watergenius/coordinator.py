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

# The device sends a full data dump ~8s after connecting.
# We wait up to 12s on first connect to capture it.
_INITIAL_WAIT = 12
_POLL_WAIT = 5


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

        The device sends two types of messages:
        1. Full dump (~845+ bytes): sent ~8s after connection, contains everything
        2. Periodic update (~42 bytes): sent every ~7s, contains key status values

        Byte offsets determined by correlating app values with binary data:

        FULL DUMP (845+ bytes):
          Offset 280: remaining_capacity_pct (1 byte, %)
          Offset 281: current_month (1 byte)
          Offset 282: current_day (1 byte)
          Offset 283-284: unknown (2 bytes)
          Offset 285: next_regen_days (1 byte)
          Offset 286-287: flow_current (2 bytes, 0 = no flow)
          Offset 288: incoming_hardness (1 byte, mg/L)
          Offset 289: padding
          Offset 290: outgoing_hardness (1 byte, mg/L)
          Offset 291: unknown
          Offset 292: valve_state (1 byte, 1=in service)
          Offset 356-357: unknown (0x0190 = 400)
          Offset 358-359: unknown (0x00C8 = 200)
          Offset 366-367: unknown (0x006E = 110)
          Offset 430-431: total_capacity (2 bytes, L) = 3315
          Offset 432-433: remaining_capacity_l (2 bytes, L) = 874
          Offset 434: regen_time_hours? (0x3C = 60)
          Offset 524-527: total_caco3 (4 bytes, g) = 3308

        PERIODIC UPDATE (42 bytes):
          Offset 35: remaining_capacity_pct (1 byte, %)
          Offset 36: current_month (1 byte)
          Offset 37: current_day (1 byte)
          Offset 38-39: counter/time (2 bytes)
        """
        if len(data) >= 300:
            self._parse_full_dump(data)
        elif len(data) >= 40:
            self._parse_periodic_update(data)
        else:
            _LOGGER.debug("Data too short to parse (%d bytes)", len(data))

    def _parse_full_dump(self, data: bytes) -> None:
        """Parse the full data dump (~845+ bytes)."""
        _LOGGER.info("Parsing full data dump (%d bytes)", len(data))

        # Remaining capacity percentage
        if len(data) > 280:
            self._data.raw["remaining_capacity_pct"] = bytes([data[280]])
            _LOGGER.info("  Remaining capacity: %d%%", data[280])

        # Date
        if len(data) > 282:
            _LOGGER.info("  Date: month=%d day=%d", data[281], data[282])

        # Next regeneration days
        if len(data) > 285:
            self._data.raw["next_regen_days"] = bytes([data[285]])
            _LOGGER.info("  Next regen: %d day(s)", data[285])

        # Current flow (2 bytes big-endian)
        if len(data) > 287:
            flow = int.from_bytes(data[286:288], "big")
            self._data.raw["flow_current"] = data[286:288]
            _LOGGER.info("  Flow: %d", flow)

        # Incoming hardness (1 byte, mg/L)
        if len(data) > 288:
            self._data.raw["incoming_hardness"] = bytes([data[288]])
            _LOGGER.info("  Incoming hardness: %d mg/L", data[288])

        # Outgoing hardness (1 byte, mg/L)
        if len(data) > 290:
            self._data.raw["outgoing_hardness"] = bytes([data[290]])
            _LOGGER.info("  Outgoing hardness: %d mg/L", data[290])

        # Valve state
        if len(data) > 292:
            self._data.raw["valve_state"] = bytes([data[292]])
            _LOGGER.info("  Valve state: %d", data[292])

        # Total capacity (2 bytes at offset 430-431)
        if len(data) > 431:
            total_cap = int.from_bytes(data[430:432], "big")
            self._data.raw["total_capacity"] = data[430:432]
            _LOGGER.info("  Total capacity: %d L", total_cap)

        # Remaining capacity in liters (2 bytes at offset 432-433)
        if len(data) > 433:
            remain_l = int.from_bytes(data[432:434], "big")
            self._data.raw["remaining_capacity_l"] = data[432:434]
            _LOGGER.info("  Remaining capacity: %d L", remain_l)

        # Total CaCO3 removed (4 bytes at offset 524-527)
        if len(data) > 527:
            caco3 = int.from_bytes(data[524:528], "big")
            self._data.raw["total_caco3"] = data[524:528]
            _LOGGER.info("  Total CaCO3: %d g", caco3)

        # Log nearby bytes for discovering more data points
        _LOGGER.debug("  Bytes 280-300: %s", data[280:300].hex())
        if len(data) > 440:
            _LOGGER.debug("  Bytes 425-445: %s", data[425:445].hex())
        if len(data) > 530:
            _LOGGER.debug("  Bytes 520-540: %s", data[520:540].hex())

    def _parse_periodic_update(self, data: bytes) -> None:
        """Parse the periodic status update (~42 bytes)."""
        _LOGGER.info("Parsing periodic update (%d bytes)", len(data))

        if len(data) > 35:
            self._data.raw["remaining_capacity_pct"] = bytes([data[35]])
            _LOGGER.info("  Remaining capacity: %d%%", data[35])

        if len(data) > 37:
            _LOGGER.info("  Date: month=%d day=%d", data[36], data[37])

        if len(data) > 39:
            counter = int.from_bytes(data[38:40], "big")
            _LOGGER.info("  Counter: %d", counter)

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
            # Wait longer on first fetch to capture the full dump
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
