"""DataUpdateCoordinator for WaterGenius integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak.backends.device import BLEDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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

        # Set up status callback
        self._ble.set_status_callback(self._handle_status)

    @property
    def address(self) -> str:
        """Return the BLE device address."""
        return self._device.address

    @property
    def device_name(self) -> str:
        """Return the device name."""
        return self._device_name

    def _handle_status(self, payload: bytes) -> None:
        """Handle incoming status report from the device.

        Parses the p0 status payload and updates device data.
        """
        _LOGGER.debug("Status payload (%d bytes): %s", len(payload), payload.hex())

        if not payload:
            return

        self._parse_status_payload(payload)

        # Schedule an HA state update
        self.async_set_updated_data(self._data)

    def _parse_status_payload(self, payload: bytes) -> None:
        """Parse a Gizwits p0 status payload into data point values.

        Data points are packed sequentially in the order defined by
        the Gizwits product schema. The exact byte layout needs
        validation against the real device.
        """
        if not payload:
            return

        # Data points in expected order in the status payload.
        # This ordering is based on the APK's data point definitions.
        dp_order = [
            ("g_uiHardness", 2),
            ("g_uiHardnessOut", 2),
            ("g_ucWaterHdUintSetUSER", 1),
            ("g_ucRegenStatus", 2),
            ("g_ulFlowCurrent", 4),
            ("g_ulRemainCap", 4),
            ("g_ulRegenFlowSet", 4),
            ("g_ucCaCO3Total", 4),
            ("g_ucCurrentSaltLevel", 1),
            ("g_usEstDaysToNext", 2),
            ("g_uiDailyWaterUsageAvg", 2),
            ("g_ucWeekRegenFlag", 1),
            ("g_ucAlarm", 1),
            ("g_ucRegenEN", 1),
            ("g_ucAlarmOnHour", 1),
            ("g_ucAlarmOnMin", 1),
            ("g_ucAlarmOffHour", 1),
            ("g_ucAlarmOffMin", 1),
            ("g_uiRegenTimeHourMin", 2),
            ("g_ucHolidayYear", 1),
            ("g_ucHolidayMon", 1),
            ("g_ucHolidayDay", 1),
            ("g_ulERRLog0", 4),
            ("g_ucL1Reserved1", 1),
        ]

        offset = 0
        parsed = 0
        for dp_name, length in dp_order:
            if offset + length > len(payload):
                break
            self._data.raw[dp_name] = payload[offset : offset + length]
            offset += length
            parsed += 1

        _LOGGER.debug(
            "Parsed %d/%d data points from payload (%d/%d bytes used)",
            parsed,
            len(dp_order),
            offset,
            len(payload),
        )

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
            # Request fresh status from device
            await self._ble.request_status()
            # Give the device time to respond via notification
            await asyncio.sleep(2)
        except Exception as err:
            _LOGGER.warning("Error requesting status: %s", err)
            await self._ble.disconnect()
            raise UpdateFailed(f"Error communicating with device: {err}") from err

        return self._data

    async def async_send_command(self, dp_name: str, value: int) -> None:
        """Send a control command to the device.

        For now, this uses a simplified approach. The actual attr_flags
        and attr_vals encoding depends on the Gizwits product schema
        and will need refinement.
        """
        if not self._ble.is_connected:
            _LOGGER.error("Cannot send command: not connected")
            return

        from .gizwits_protocol import DATA_POINTS, number2bytes

        dp = DATA_POINTS.get(dp_name)
        if dp is None or not dp.writable:
            _LOGGER.error("Cannot write to data point: %s", dp_name)
            return

        try:
            value_bytes = number2bytes(value, dp.byte_length)
            # Simplified: send value directly as attr_flags + attr_vals
            # This needs refinement based on actual Gizwits schema
            await self._ble.write_control(
                attr_flags=b"\xFF",  # placeholder
                attr_vals=value_bytes,
            )
            # Request updated status after command
            await asyncio.sleep(1)
            await self._ble.request_status()
        except Exception:
            _LOGGER.exception("Error sending command %s=%d", dp_name, value)

    async def async_shutdown(self) -> None:
        """Disconnect from the device on shutdown."""
        await self._ble.disconnect()
