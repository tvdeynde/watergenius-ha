"""Gizwits GAgent BLE communication for WaterGenius devices.

The device uses a proprietary binary protocol over BLE GATT, NOT the
standard Gizwits MCU serial protocol. Data is sent as a raw binary dump
split across multiple 128-byte BLE packets on a single characteristic
(0xABF7) that serves as both write and notify.

Service UUID: 0xABF0
Read/Write/Notify characteristic: 0xABF7
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice

from .const import NOTIFY_UUID, WRITE_UUID

_LOGGER = logging.getLogger(__name__)

# BLE MTU chunk size — the device sends data in 128-byte chunks
_BLE_CHUNK_SIZE = 128

# Time window to consider packets as part of the same dump (seconds)
_PACKET_GROUP_TIMEOUT = 1.0


class GizwitsBleConnection:
    """Manages a BLE connection to a Gizwits GAgent device."""

    def __init__(self, device: BLEDevice) -> None:
        """Initialize the connection."""
        self._device = device
        self._client: BleakClient | None = None
        self._connected = False
        self._status_callback: Callable[[bytes], None] | None = None
        self._notify_uuid: str = NOTIFY_UUID
        self._write_uuid: str = WRITE_UUID

        # Buffer for reassembling multi-packet data dumps
        self._receive_buffer: bytearray = bytearray()
        self._last_packet_time: float = 0
        self._flush_task: asyncio.TimerHandle | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if connected."""
        return (
            self._connected
            and self._client is not None
            and self._client.is_connected
        )

    def set_status_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for incoming data dumps.

        The callback receives the full reassembled binary data.
        """
        self._status_callback = callback

    async def connect(self) -> bool:
        """Connect to the device and subscribe to notifications."""
        try:
            self._client = BleakClient(self._device, timeout=30.0)
            await self._client.connect()
            self._connected = True

            _LOGGER.info(
                "Connected to WaterGenius device %s (%s)",
                self._device.name,
                self._device.address,
            )

            # Log all services and characteristics
            for service in self._client.services:
                _LOGGER.debug(
                    "Service: %s (UUID: %s)", service.description, service.uuid
                )
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    _LOGGER.debug(
                        "  Char: %s (UUID: %s) [%s]",
                        char.description,
                        char.uuid,
                        props,
                    )

            # Find the notify/write characteristic dynamically
            notify_char = None
            write_char = None
            for service in self._client.services:
                for char in service.characteristics:
                    if "notify" in char.properties and not notify_char:
                        notify_char = char.uuid
                    if (
                        "write-without-response" in char.properties
                        or "write" in char.properties
                    ) and not write_char:
                        write_char = char.uuid

            if not notify_char:
                _LOGGER.error("No notify characteristic found on device!")
                await self.disconnect()
                return False

            self._notify_uuid = notify_char
            self._write_uuid = write_char or notify_char
            _LOGGER.info(
                "Using characteristic: notify=%s write=%s",
                self._notify_uuid,
                self._write_uuid,
            )

            # Subscribe to notifications
            await self._client.start_notify(
                self._notify_uuid, self._handle_notification
            )
            _LOGGER.info("Subscribed to notifications")

            return True

        except Exception:
            _LOGGER.exception("Failed to connect to %s", self._device.address)
            await self.disconnect()
            return False

    def _handle_notification(self, _sender: int, data: bytearray) -> None:
        """Handle incoming BLE notification.

        The device sends data as multiple 128-byte chunks. We buffer them
        and flush when we receive a short packet (end of dump) or after
        a timeout.
        """
        now = time.monotonic()
        data_bytes = bytes(data)

        _LOGGER.debug(
            "BLE packet (%d bytes): %s", len(data_bytes), data_bytes.hex()
        )

        # Skip the initial 2-byte "ffff" handshake
        if len(data_bytes) <= 2:
            _LOGGER.debug("Handshake/short packet, skipping")
            return

        # Check if this is a new data group or continuation
        if (
            self._receive_buffer
            and now - self._last_packet_time > _PACKET_GROUP_TIMEOUT
        ):
            # Previous group timed out, flush it first
            self._flush_buffer()

        self._receive_buffer.extend(data_bytes)
        self._last_packet_time = now

        # If packet is shorter than MTU, it's the last chunk
        if len(data_bytes) < _BLE_CHUNK_SIZE:
            self._flush_buffer()
        else:
            # Schedule a flush in case no more packets arrive
            if self._flush_task:
                self._flush_task.cancel()
            loop = asyncio.get_event_loop()
            self._flush_task = loop.call_later(
                _PACKET_GROUP_TIMEOUT, self._flush_buffer
            )

    def _flush_buffer(self) -> None:
        """Process the complete reassembled data dump."""
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None

        if not self._receive_buffer:
            return

        data = bytes(self._receive_buffer)
        self._receive_buffer.clear()

        _LOGGER.info(
            "Complete data dump received (%d bytes)", len(data)
        )
        _LOGGER.debug("Full dump hex: %s", data.hex())

        if self._status_callback:
            self._status_callback(data)

    async def request_status(self) -> None:
        """Request the device to report its current status.

        The device appears to send data dumps periodically on its own
        after connection. We can also try writing a simple request.
        """
        if not self._client or not self._client.is_connected:
            return

        # The device sends data automatically after connection.
        # Try sending a minimal request to trigger a fresh dump.
        try:
            await self._client.write_gatt_char(
                self._write_uuid, b"\x00\x00", response=False
            )
        except Exception:
            _LOGGER.debug("Could not write status request")

    async def write_command(self, data: bytes) -> None:
        """Write raw data to the device."""
        if not self._client or not self._client.is_connected:
            _LOGGER.error("Cannot write: not connected")
            return

        await self._client.write_gatt_char(
            self._write_uuid, data, response=False
        )
        _LOGGER.debug("Wrote %d bytes: %s", len(data), data.hex())

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        self._connected = False
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                _LOGGER.debug("Error during disconnect", exc_info=True)
            self._client = None
