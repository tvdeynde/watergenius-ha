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
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import NOTIFY_UUID, SERVICE_UUID, WRITE_UUID

_LOGGER = logging.getLogger(__name__)

# BLE MTU chunk size — the device sends data in 128-byte chunks
_BLE_CHUNK_SIZE = 128

# Time window to consider packets as part of the same dump (seconds)
_PACKET_GROUP_TIMEOUT = 1.0

# Maximum reassembly buffer size (bytes). The Gizwits payload is 807 bytes
# plus a 38-byte header = 845 bytes. We allow some headroom but cap to
# prevent unbounded memory growth from a misbehaving or spoofed device.
_MAX_BUFFER_SIZE = 2048

# Expected WaterGenius characteristic UUID
_EXPECTED_CHAR_UUID = "0000abf7-0000-1000-8000-00805f9b34fb"


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

        # Set whenever a complete dump has been flushed to the callback
        self._dump_event = asyncio.Event()

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

    def set_device(self, device: BLEDevice) -> None:
        """Replace the BLEDevice (re-resolved before each reconnect)."""
        self._device = device

    def clear_dump_event(self) -> None:
        """Reset the dump-received event before requesting new data."""
        self._dump_event.clear()

    async def wait_for_dump(self, timeout: float) -> bool:
        """Wait until a complete dump arrives or the timeout expires."""
        try:
            await asyncio.wait_for(self._dump_event.wait(), timeout)
        except TimeoutError:
            return False
        return True

    async def connect(self) -> bool:
        """Connect to the device and subscribe to notifications."""
        try:
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                self._device,
                self._device.name or self._device.address,
            )
            self._connected = True

            _LOGGER.debug(
                "Connected to %s (%s)",
                self._device.name,
                self._device.address,
            )

            # Find the notify/write characteristic, preferring the known
            # WaterGenius UUID (ABF7) under the expected service (ABF0).
            notify_char = None
            write_char = None

            for service in self._client.services:
                for char in service.characteristics:
                    # Prefer the known characteristic UUID
                    if char.uuid.lower() == _EXPECTED_CHAR_UUID:
                        if "notify" in char.properties:
                            notify_char = char.uuid
                        if (
                            "write-without-response" in char.properties
                            or "write" in char.properties
                        ):
                            write_char = char.uuid

            # Fallback: search under the ABF0 service
            if not notify_char:
                for service in self._client.services:
                    if SERVICE_UUID.lower() not in service.uuid.lower():
                        continue
                    for char in service.characteristics:
                        if "notify" in char.properties and not notify_char:
                            notify_char = char.uuid
                        if (
                            "write-without-response" in char.properties
                            or "write" in char.properties
                        ) and not write_char:
                            write_char = char.uuid

            if not notify_char:
                _LOGGER.error("No notify characteristic found on device")
                await self.disconnect()
                return False

            self._notify_uuid = notify_char
            self._write_uuid = write_char or notify_char
            _LOGGER.debug(
                "Using characteristics: notify=%s write=%s",
                self._notify_uuid,
                self._write_uuid,
            )

            # Subscribe to notifications
            await self._client.start_notify(
                self._notify_uuid, self._handle_notification
            )

            return True

        except Exception:
            _LOGGER.exception("Failed to connect to %s", self._device.address)
            await self.disconnect()
            return False

    def _handle_notification(self, _sender: int, data: bytearray) -> None:
        """Handle incoming BLE notification.

        The device sends data as multiple 128-byte chunks. We buffer them
        and flush when we receive a short packet (end of dump) or after
        a timeout. The buffer is capped to prevent memory exhaustion.
        """
        now = time.monotonic()
        data_bytes = bytes(data)

        _LOGGER.debug("BLE packet (%d bytes)", len(data_bytes))

        # Skip the initial 2-byte handshake
        if len(data_bytes) <= 2:
            return

        # Check if this is a new data group or continuation
        if (
            self._receive_buffer
            and now - self._last_packet_time > _PACKET_GROUP_TIMEOUT
        ):
            self._flush_buffer()

        # Cap buffer size to prevent unbounded growth
        if len(self._receive_buffer) + len(data_bytes) > _MAX_BUFFER_SIZE:
            _LOGGER.warning(
                "Buffer overflow (%d + %d > %d), dropping frame",
                len(self._receive_buffer),
                len(data_bytes),
                _MAX_BUFFER_SIZE,
            )
            self._receive_buffer.clear()
            if self._flush_task:
                self._flush_task.cancel()
                self._flush_task = None
            return

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

        _LOGGER.debug("Data dump received (%d bytes)", len(data))

        if self._status_callback:
            self._status_callback(data)
        self._dump_event.set()

    async def request_status(self) -> None:
        """Request the device to report its current status."""
        if not self._client or not self._client.is_connected:
            return

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
        _LOGGER.debug("Wrote %d bytes", len(data))

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
