"""Gizwits GAgent BLE protocol implementation for WaterGenius devices.

The device uses the Gizwits GAgent BLE SPP (Serial Port Profile) protocol,
which is a transparent serial bridge over BLE GATT. The protocol is unencrypted
and uses simple framing with a header, length, command, and checksum.

Service UUID: 0xABF0
Write characteristic: 0xABF1 (send commands to device)
Notify characteristic: 0xABF2 (receive data from device)

Packet format:
    | header(0xFFFF) | len(2B) | cmd(1B) | sn(1B) | flags(2B) | payload | checksum(1B) |

Reference: Gizwits GAgent source (gagent.h), GizwitsBLE SDK
"""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice

from .const import (
    ACTION_CONTROL,
    ACTION_READ_STATUS,
    ACTION_READ_STATUS_ACK,
    ACTION_REPORT_STATUS,
    CMD_CTRL,
    CMD_HEARTBEAT,
    CMD_HEARTBEAT_ACK,
    CMD_REPORT,
    CMD_REPORT_ACK,
    GIZWITS_HEADER,
    NOTIFY_UUID,
    WRITE_UUID,
)

_LOGGER = logging.getLogger(__name__)


def _checksum(data: bytes) -> int:
    """Compute Gizwits packet checksum (sum of all bytes from len onward, mod 256)."""
    return sum(data) & 0xFF


def _build_packet(cmd: int, sn: int, payload: bytes = b"") -> bytes:
    """Build a Gizwits protocol packet.

    Format: header(2) + len(2) + cmd(1) + sn(1) + flags(2) + payload(N) + checksum(1)
    Length covers cmd through checksum (inclusive).
    """
    flags = b"\x00\x00"
    # len = cmd(1) + sn(1) + flags(2) + payload(N) + checksum(1)
    length = 1 + 1 + 2 + len(payload) + 1
    body = struct.pack(">H", length) + bytes([cmd, sn]) + flags + payload
    chk = _checksum(body)
    return GIZWITS_HEADER + body + bytes([chk])


def _parse_packet(data: bytes) -> tuple[int, int, bytes] | None:
    """Parse a Gizwits protocol packet.

    Returns (cmd, sn, payload) or None if invalid.
    """
    if len(data) < 8:
        return None

    # Check header
    if data[0:2] != GIZWITS_HEADER:
        _LOGGER.debug("Invalid header: %s", data[0:2].hex())
        return None

    length = struct.unpack(">H", data[2:4])[0]
    cmd = data[4]
    sn = data[5]
    # flags at data[6:8]

    # Payload is everything between flags and checksum
    # Total packet = header(2) + len_field(2) + body(length)
    # body = cmd(1) + sn(1) + flags(2) + payload(N) + checksum(1)
    # So payload length = length - 5
    payload_len = length - 5
    if payload_len < 0:
        payload_len = 0

    payload = data[8 : 8 + payload_len] if payload_len > 0 else b""

    # Verify checksum
    expected_chk = data[2 + 2 + length - 1] if (2 + 2 + length - 1) < len(data) else None
    if expected_chk is not None:
        actual_chk = _checksum(data[2 : 2 + 2 + length - 1])
        if actual_chk != expected_chk:
            _LOGGER.debug(
                "Checksum mismatch: expected=0x%02X actual=0x%02X",
                expected_chk,
                actual_chk,
            )

    return cmd, sn, payload


class GizwitsBleConnection:
    """Manages a BLE connection to a Gizwits GAgent device."""

    def __init__(self, device: BLEDevice) -> None:
        """Initialize the connection."""
        self._device = device
        self._client: BleakClient | None = None
        self._connected = False
        self._sn: int = 0
        self._status_callback: Callable[[bytes], None] | None = None
        self._receive_buffer: bytearray = bytearray()
        self._notify_uuid: str = NOTIFY_UUID
        self._write_uuid: str = WRITE_UUID

    @property
    def is_connected(self) -> bool:
        """Return True if connected."""
        return self._connected and self._client is not None and self._client.is_connected

    def set_status_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for incoming status reports.

        The callback receives the raw p0 payload (after the action byte).
        """
        self._status_callback = callback

    def _next_sn(self) -> int:
        """Get next sequence number."""
        self._sn = (self._sn + 1) & 0xFF
        return self._sn

    async def connect(self) -> bool:
        """Connect to the device and subscribe to notifications.

        Returns True on success.
        """
        try:
            self._client = BleakClient(self._device, timeout=30.0)
            await self._client.connect()
            self._connected = True

            _LOGGER.info(
                "Connected to WaterGenius device %s (%s)",
                self._device.name,
                self._device.address,
            )

            # Log all available services and characteristics for debugging
            for service in self._client.services:
                _LOGGER.info(
                    "Service: %s (UUID: %s)", service.description, service.uuid
                )
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    _LOGGER.info(
                        "  Characteristic: %s (UUID: %s) [%s]",
                        char.description,
                        char.uuid,
                        props,
                    )

            # Find the notify characteristic dynamically
            notify_char = None
            write_char = None
            for service in self._client.services:
                if "abf0" in service.uuid.lower():
                    for char in service.characteristics:
                        if "notify" in char.properties:
                            notify_char = char.uuid
                            _LOGGER.info("Found notify characteristic: %s", char.uuid)
                        if "write-without-response" in char.properties or "write" in char.properties:
                            write_char = char.uuid
                            _LOGGER.info("Found write characteristic: %s", char.uuid)

            # If not found under ABF0, search all services
            if not notify_char:
                for service in self._client.services:
                    for char in service.characteristics:
                        if "notify" in char.properties:
                            notify_char = char.uuid
                            _LOGGER.info(
                                "Found notify characteristic (fallback): %s in service %s",
                                char.uuid,
                                service.uuid,
                            )
                            break
                    if notify_char:
                        break

            if not write_char:
                for service in self._client.services:
                    for char in service.characteristics:
                        if "write-without-response" in char.properties or "write" in char.properties:
                            write_char = char.uuid
                            _LOGGER.info(
                                "Found write characteristic (fallback): %s in service %s",
                                char.uuid,
                                service.uuid,
                            )
                            break
                    if write_char:
                        break

            if not notify_char:
                _LOGGER.error("No notify characteristic found on device!")
                await self.disconnect()
                return False

            self._notify_uuid = notify_char
            self._write_uuid = write_char or WRITE_UUID

            # Subscribe to notifications
            await self._client.start_notify(self._notify_uuid, self._handle_notification)
            _LOGGER.info("Subscribed to notifications on %s", self._notify_uuid)

            # Send heartbeat to verify communication
            await asyncio.sleep(0.5)
            await self._send_heartbeat()

            return True

        except Exception:
            _LOGGER.exception("Failed to connect to %s", self._device.address)
            await self.disconnect()
            return False

    def _handle_notification(self, _sender: int, data: bytearray) -> None:
        """Handle incoming BLE notification."""
        _LOGGER.info(
            "BLE notification (%d bytes): %s", len(data), bytes(data).hex()
        )

        # Short packets (< 4 bytes) - log and skip
        if len(data) < 4:
            _LOGGER.debug("Short notification, skipping parse")
            return

        # Handle fragmented packets (Gizwits uses "##" prefix for fragments)
        if len(data) > 2 and data[0:2] == b"##":
            total = data[2]
            current = data[3]
            self._receive_buffer.extend(data[4:])
            _LOGGER.debug("Fragment %d/%d", current + 1, total)
            if current < total - 1:
                return
            data = bytearray(self._receive_buffer)
            self._receive_buffer.clear()
            _LOGGER.info("Reassembled packet (%d bytes): %s", len(data), bytes(data).hex())
        else:
            self._receive_buffer.clear()

        result = _parse_packet(bytes(data))
        if result is None:
            _LOGGER.warning(
                "Could not parse notification packet: %s", bytes(data).hex()
            )
            return

        cmd, sn, payload = result
        _LOGGER.info(
            "Parsed packet: cmd=0x%02X sn=%d payload(%d bytes)=%s",
            cmd,
            sn,
            len(payload),
            payload.hex(),
        )

        if cmd == CMD_REPORT and len(payload) > 0:
            # Device status report
            action = payload[0]
            if action in (ACTION_REPORT_STATUS, ACTION_READ_STATUS_ACK):
                status_data = payload[1:]
                _LOGGER.debug("Status report (%d bytes): %s", len(status_data), status_data.hex())
                if self._status_callback:
                    self._status_callback(status_data)

            # Send ACK
            asyncio.get_event_loop().create_task(
                self._send_packet(CMD_REPORT_ACK, sn=sn)
            )

        elif cmd == CMD_HEARTBEAT_ACK:
            _LOGGER.debug("Heartbeat ACK received")

        elif cmd == CMD_HEARTBEAT:
            # Device sent heartbeat, respond with ACK
            asyncio.get_event_loop().create_task(
                self._send_packet(CMD_HEARTBEAT_ACK, sn=sn)
            )

    async def _send_packet(
        self, cmd: int, payload: bytes = b"", sn: int | None = None
    ) -> None:
        """Send a Gizwits protocol packet to the device."""
        if not self._client or not self._client.is_connected:
            _LOGGER.error("Cannot send: not connected")
            return

        if sn is None:
            sn = self._next_sn()

        packet = _build_packet(cmd, sn, payload)
        _LOGGER.debug("Sending: cmd=0x%02X sn=%d data=%s", cmd, sn, packet.hex())

        await self._client.write_gatt_char(self._write_uuid, packet, response=False)

    async def _send_heartbeat(self) -> None:
        """Send a heartbeat ping to the device."""
        await self._send_packet(CMD_HEARTBEAT)

    async def request_status(self) -> None:
        """Request the device to report its current status.

        Tries multiple approaches since the exact protocol variant may differ.
        """
        # Approach 1: Standard Gizwits status read request
        payload = bytes([ACTION_READ_STATUS])
        await self._send_packet(CMD_CTRL, payload)
        await asyncio.sleep(0.5)

        # Approach 2: Try reading the characteristic directly
        if self._client and self._client.is_connected:
            try:
                read_data = await self._client.read_gatt_char(self._write_uuid)
                _LOGGER.info(
                    "Read from characteristic (%d bytes): %s",
                    len(read_data),
                    bytes(read_data).hex(),
                )
            except Exception:
                _LOGGER.debug("Could not read characteristic directly")

    async def write_control(self, attr_flags: bytes, attr_vals: bytes) -> None:
        """Send a control command to set data point values.

        Args:
            attr_flags: Bitmask indicating which data points to set.
            attr_vals: Values for the flagged data points.
        """
        payload = bytes([ACTION_CONTROL]) + attr_flags + attr_vals
        await self._send_packet(CMD_CTRL, payload)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        self._connected = False
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                _LOGGER.debug("Error during disconnect", exc_info=True)
            self._client = None
