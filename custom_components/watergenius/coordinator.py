"""DataUpdateCoordinator for WaterGenius integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak.backends.device import BLEDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_MESH_LTK, DEFAULT_MESH_NAME, DEFAULT_MESH_PASSWORD, DEFAULT_SCAN_INTERVAL, DOMAIN
from .gizwits_protocol import WaterGeniusDeviceData
from .telink_mesh import TelinkMeshConnection

_LOGGER = logging.getLogger(__name__)


class WaterGeniusCoordinator(DataUpdateCoordinator[WaterGeniusDeviceData | None]):
    """Coordinator for polling WaterGenius device data over BLE."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: BLEDevice,
        device_name: str,
        mesh_name: str = DEFAULT_MESH_NAME,
        mesh_password: str = DEFAULT_MESH_PASSWORD,
        mesh_ltk: bytes = DEFAULT_MESH_LTK,
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
        self._mesh = TelinkMeshConnection(
            device=device,
            mesh_name=mesh_name,
            mesh_password=mesh_password,
            mesh_ltk=mesh_ltk,
        )
        self._data = WaterGeniusDeviceData()
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5

        # Set up notification callback
        self._mesh.set_notification_callback(self._handle_notification)

    @property
    def address(self) -> str:
        """Return the BLE device address."""
        return self._device.address

    @property
    def device_name(self) -> str:
        """Return the device name."""
        return self._device_name

    def _handle_notification(self, data: bytes) -> None:
        """Handle incoming BLE notification with device data.

        Parses the decrypted notification payload and updates the device data.
        The exact payload format depends on the Gizwits mesh protocol.
        This is a best-effort parser that will be refined with real device data.
        """
        _LOGGER.debug("Received notification: %s", data.hex())

        if len(data) < 10:
            return

        # The notification payload after Telink mesh header contains
        # Gizwits data point updates. The exact format needs validation
        # with a real device, but typically:
        # - Bytes 7+: opcode + vendor + data point payload
        opcode = data[7] if len(data) > 7 else 0

        # Status report opcodes (vendor-specific, varies by implementation)
        if opcode in (0xDB, 0xDC, 0xDD, 0xDE):
            payload = data[10:] if len(data) > 10 else b""
            self._parse_status_payload(payload)

            # Schedule an HA state update
            self.hass.loop.call_soon_threadsafe(
                self.async_set_updated_data, self._data
            )

    def _parse_status_payload(self, payload: bytes) -> None:
        """Parse a Gizwits status payload into data point values.

        The payload contains data point values in a defined order.
        The exact byte layout needs validation against a real device.

        NOTE: This parser assumes data points are packed sequentially
        in the order defined in the Gizwits product schema. The actual
        order and encoding may differ - this will need adjustment after
        testing with a real device.
        """
        if not payload:
            return

        from .gizwits_protocol import DATA_POINTS

        # Map of data points in their expected order in the status payload.
        # This ordering is based on the APK's data point definitions.
        # Each entry is (dp_name, byte_length).
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
        for dp_name, length in dp_order:
            if offset + length > len(payload):
                break
            self._data.raw[dp_name] = payload[offset : offset + length]
            offset += length

        _LOGGER.debug(
            "Parsed %d data points from payload (%d bytes)",
            len([dp for dp in dp_order if dp[0] in self._data.raw]),
            len(payload),
        )

    async def _async_update_data(self) -> WaterGeniusDeviceData | None:
        """Fetch data from the device via BLE."""
        # Ensure connection
        if not self._mesh.is_connected:
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
            connected = await self._mesh.connect()
            if not connected:
                raise UpdateFailed("Failed to connect to WaterGenius device")
            self._reconnect_attempts = 0

        try:
            # Request fresh status from device
            await self._mesh.request_status()
            # Give the device a moment to send notification responses
            await asyncio.sleep(2)
        except Exception as err:
            _LOGGER.warning("Error requesting status: %s", err)
            # Connection likely lost, disconnect to trigger reconnect next cycle
            await self._mesh.disconnect()
            raise UpdateFailed(f"Error communicating with device: {err}") from err

        return self._data

    async def async_send_command(self, dp_name: str, value: int) -> None:
        """Send a control command to the device."""
        if not self._mesh.is_connected:
            _LOGGER.error("Cannot send command: not connected")
            return

        try:
            await self._mesh.write_data_point(dp_name, value)
            # Request updated status after command
            await asyncio.sleep(1)
            await self._mesh.request_status()
        except Exception:
            _LOGGER.exception("Error sending command %s=%d", dp_name, value)

    async def async_shutdown(self) -> None:
        """Disconnect from the device on shutdown."""
        await self._mesh.disconnect()
