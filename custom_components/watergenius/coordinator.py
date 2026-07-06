"""DataUpdateCoordinator for WaterGenius integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from bleak.backends.device import BLEDevice
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, PRODUCT_KEYS
from .gizwits_ble import GizwitsBleConnection
from .gizwits_protocol import WaterGeniusDeviceData

_LOGGER = logging.getLogger(__name__)

# BLE data = 38-byte header + 807-byte Gizwits payload
# Header offset verified by matching product key and hardness values
_HEADER_SIZE = 38
_FULL_DUMP_SIZE = _HEADER_SIZE + 807

# Header signature: bytes 10-37 of a full dump are 0xFF padding. Used to
# locate the frame when packet grouping merges stray chunks in front of it.
_HEADER_PADDING = b"\xff" * 28
_HEADER_PADDING_OFFSET = 10

# The device sends a full data dump ~8s after connecting.
_INITIAL_WAIT = 15
_POLL_WAIT = 6

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
        self._first_fetch = True
        self._last_dump: bytes | None = None

        self._ble.set_status_callback(self._handle_data_dump)

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def last_dump(self) -> bytes | None:
        """Return the most recent full data dump (for diagnostics)."""
        return self._last_dump

    @staticmethod
    def _extract_frame(data: bytes) -> bytes | None:
        """Locate the 845-byte dump frame inside the reassembled buffer.

        Packet grouping is timing-based, so stray chunks (e.g. a late
        fragment of a previous message) can end up prepended to the
        frame. Absolute offsets then shift and every value parses as
        garbage. Anchor on the header's 0xFF padding signature instead
        of trusting the buffer start.
        """
        idx = data.rfind(_HEADER_PADDING)
        if idx < _HEADER_PADDING_OFFSET:
            return None
        start = idx - _HEADER_PADDING_OFFSET
        frame = data[start : start + _FULL_DUMP_SIZE]
        if len(frame) < _FULL_DUMP_SIZE:
            return None
        # Every full dump embeds the Gizwits product key as an ASCII
        # string; require it as a second anchor before trusting offsets.
        if not any(pk.encode() in frame for pk in PRODUCT_KEYS):
            return None
        return frame

    def _handle_data_dump(self, data: bytes) -> None:
        """Handle incoming data dump from the device."""
        _LOGGER.debug("Received data dump (%d bytes)", len(data))
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
        if len(data) >= _FULL_DUMP_SIZE:
            frame = self._extract_frame(data)
            if frame is None:
                _LOGGER.debug(
                    "No valid frame signature in %d-byte dump, skipping",
                    len(data),
                )
                return
            self._last_dump = frame
            self._parse_full_dump(frame)
        elif len(data) >= 40:
            self._parse_periodic_update(data)
        else:
            _LOGGER.debug("Data too short to parse (%d bytes)", len(data))

    def _parse_full_dump(self, data: bytes) -> None:
        """Parse the full data dump using Gizwits schema offsets."""
        _LOGGER.debug("Parsing full data dump (%d bytes)", len(data))

        for p_offset, length, name, _desc in _DATA_POINTS:
            ble_offset = p_offset + _HEADER_SIZE
            if ble_offset + length <= len(data):
                self._data.raw[name] = data[ble_offset : ble_offset + length]

        # Calculate remaining capacity percentage
        total = self._data.total_capacity
        remain = self._data.remaining_capacity
        if total and remain and total > 0:
            pct = int(remain * 100 / total)
            self._data.raw["remaining_capacity_pct"] = bytes([min(pct, 100)])

    def _parse_periodic_update(self, data: bytes) -> None:
        """Parse the periodic status update (~42 bytes).

        These short updates contain a condensed status. The exact
        mapping is still being refined, but we can extract the
        remaining capacity percentage from position 35.
        """
        _LOGGER.debug("Parsing periodic update (%d bytes)", len(data))

    async def _async_update_data(self) -> WaterGeniusDeviceData | None:
        """Fetch data from the device via BLE."""
        if not self._ble.is_connected:
            # Re-resolve the BLEDevice: a cached device goes stale once the
            # device drops out of range and comes back.
            device = async_ble_device_from_address(
                self.hass, self._device.address, connectable=True
            )
            if device is None:
                raise UpdateFailed(
                    f"Device {self._device.address} not found by any"
                    " connectable Bluetooth adapter"
                )
            self._device = device
            self._ble.set_device(device)
            connected = await self._ble.connect()
            if not connected:
                raise UpdateFailed("Failed to connect to WaterGenius device")

        try:
            self._ble.clear_dump_event()
            await self._ble.request_status()
            wait = _INITIAL_WAIT if self._first_fetch else _POLL_WAIT
            self._first_fetch = False
            received = await self._ble.wait_for_dump(wait)
            if not received:
                _LOGGER.debug("No data dump within %d seconds", wait)
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
