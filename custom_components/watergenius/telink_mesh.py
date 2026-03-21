"""Telink BLE Mesh protocol implementation for WaterGenius devices.

Implements the Telink mesh pairing, encryption, and communication protocol
using the bleak BLE library. Based on the protocol documented in:
- google/python-dimond
- Leiaz/python-awox-mesh-light
- vpaeder/telinkpp

The protocol uses AES-128-ECB with reversed byte order for key exchange
and AES-CBC-MAC + AES-CTR for packet encryption.
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from Crypto.Cipher import AES

from .const import (
    COMMAND_UUID,
    DEFAULT_MESH_LTK,
    DEFAULT_MESH_NAME,
    DEFAULT_MESH_PASSWORD,
    NOTIFY_UUID,
    PAIR_UUID,
)

_LOGGER = logging.getLogger(__name__)


# --- Core crypto primitives (Telink uses reversed byte order for AES) ---


def _encrypt(key: bytes, data: bytes) -> bytearray:
    """AES-128-ECB encrypt with Telink's reversed byte order.

    Both key and data are reversed before encryption, and the result
    is reversed back. This bridges Telink's little-endian representation
    with AES's big-endian operation.
    """
    k = bytearray(key)
    val = bytearray(data.ljust(16, b"\x00")[:16])
    k.reverse()
    val.reverse()
    cipher = AES.new(bytes(k), AES.MODE_ECB)
    result = bytearray(cipher.encrypt(bytes(val)))
    result.reverse()
    return result


def _make_checksum(key: bytes, nonce: bytes, payload: bytes) -> bytearray:
    """Compute AES-CBC-MAC checksum for a command packet."""
    base = bytearray(nonce) + bytearray([len(payload)])
    base = base.ljust(16, b"\x00")
    check = _encrypt(key, bytes(base))
    for i in range(0, len(payload), 16):
        chunk = bytearray(payload[i : i + 16].ljust(16, b"\x00"))
        check = bytearray(a ^ b for a, b in zip(check, chunk))
        check = _encrypt(key, bytes(check))
    return check


def _crypt_payload(key: bytes, nonce: bytes, payload: bytes) -> bytearray:
    """Encrypt/decrypt payload using AES-CTR mode."""
    base = bytearray(b"\x00") + bytearray(nonce)
    base = bytearray(base.ljust(16, b"\x00"))
    result = bytearray()
    for i in range(0, len(payload), 16):
        enc_base = _encrypt(key, bytes(base))
        chunk = bytearray(payload[i : i + 16])
        result += bytearray(a ^ b for a, b in zip(enc_base, chunk))
        base[0] += 1
    return result


def _mac_bytes_reversed(address: str) -> bytearray:
    """Parse BLE MAC address string to reversed byte array."""
    addr_str = address.replace(":", "").replace("-", "")
    a = bytearray.fromhex(addr_str)
    a.reverse()
    return a


# --- Pairing ---


def _make_pair_packet(
    mesh_name: str, mesh_password: str, session_random: bytes
) -> bytearray:
    """Build the pair request packet.

    Format: [0x0C] + session_random(8) + encrypt(session_random, name^password)[0:8]
    """
    m_n = bytearray(mesh_name.encode("utf-8").ljust(16, b"\x00")[:16])
    m_p = bytearray(mesh_password.encode("utf-8").ljust(16, b"\x00")[:16])
    name_pass = bytearray(a ^ b for a, b in zip(m_n, m_p))
    s_r = bytes(session_random).ljust(16, b"\x00")
    enc = _encrypt(s_r, bytes(name_pass))
    packet = bytearray(b"\x0c") + bytearray(session_random) + enc[0:8]
    return packet


def _make_session_key(
    mesh_name: str,
    mesh_password: str,
    session_random: bytes,
    response_random: bytes,
) -> bytearray:
    """Derive the session key from credentials and nonces.

    session_key = encrypt(name^password, session_random + response_random)
    """
    m_n = bytearray(mesh_name.encode("utf-8").ljust(16, b"\x00")[:16])
    m_p = bytearray(mesh_password.encode("utf-8").ljust(16, b"\x00")[:16])
    name_pass = bytearray(a ^ b for a, b in zip(m_n, m_p))
    random_data = bytes(session_random[:8]) + bytes(response_random[:8])
    return _encrypt(bytes(name_pass), random_data)


# --- Command packet construction ---


def _make_command_packet(
    key: bytes,
    address: str,
    dest_id: int,
    opcode: int,
    data: bytes = b"",
) -> bytearray:
    """Build an encrypted command packet.

    Packet format (20 bytes):
    - Bytes 0-2: Sequence number (random)
    - Bytes 3-4: Checksum (first 2 bytes of AES-CBC-MAC)
    - Bytes 5-6: Destination mesh ID (LE uint16)
    - Byte 7: Command opcode
    - Bytes 8-9: Vendor ID (0x60, 0x01 for generic Telink)
    - Bytes 10-19: Command data
    """
    seq = os.urandom(3)
    a = _mac_bytes_reversed(address)
    nonce = bytes(a[0:4]) + b"\x01" + bytes(seq)

    # Build plaintext payload (15 bytes)
    dest = struct.pack("<H", dest_id)
    vendor = b"\x60\x01"
    payload = bytearray(dest + struct.pack("B", opcode) + vendor + bytearray(data))
    payload = bytearray(payload.ljust(15, b"\x00")[:15])

    # Compute checksum and encrypt
    check = _make_checksum(key, nonce, bytes(payload))
    encrypted = _crypt_payload(key, nonce, bytes(payload))

    # Assemble packet
    packet = bytearray(seq) + check[0:2] + encrypted
    return packet


def _decrypt_notification(
    key: bytes, address: str, packet: bytes
) -> bytearray | None:
    """Decrypt a notification packet from the device.

    Returns the decrypted payload, or None if checksum fails.
    """
    if len(packet) < 8:
        return None

    a = _mac_bytes_reversed(address)
    nonce = bytes(a[0:3]) + bytes(packet[0:5])

    decrypted = _crypt_payload(key, nonce, packet[7:])

    check = _make_checksum(key, nonce, bytes(decrypted))
    if check[0:2] != bytearray(packet[5:7]):
        _LOGGER.debug("Notification checksum mismatch")
        return None

    return bytearray(packet[0:7]) + decrypted


class TelinkMeshConnection:
    """Manages a BLE connection to a Telink mesh device."""

    def __init__(
        self,
        device: BLEDevice,
        mesh_name: str = DEFAULT_MESH_NAME,
        mesh_password: str = DEFAULT_MESH_PASSWORD,
        mesh_ltk: bytes = DEFAULT_MESH_LTK,
    ) -> None:
        """Initialize the mesh connection."""
        self._device = device
        self._mesh_name = mesh_name
        self._mesh_password = mesh_password
        self._mesh_ltk = mesh_ltk
        self._client: BleakClient | None = None
        self._session_key: bytearray | None = None
        self._sequence: int = 1
        self._notification_callback: Callable[[bytearray], None] | None = None
        self._connected = False
        self._paired = False

    @property
    def is_connected(self) -> bool:
        """Return True if connected and paired."""
        return self._connected and self._paired

    def set_notification_callback(
        self, callback: Callable[[bytearray], None]
    ) -> None:
        """Set callback for incoming notifications."""
        self._notification_callback = callback

    async def connect(self) -> bool:
        """Connect to the device, pair, and subscribe to notifications.

        Returns True on success.
        """
        try:
            self._client = BleakClient(self._device, timeout=30.0)
            await self._client.connect()
            self._connected = True

            _LOGGER.debug(
                "Connected to %s, starting pairing", self._device.address
            )

            # Pair (session key exchange)
            paired = await self._pair()
            if not paired:
                _LOGGER.error("Pairing failed with %s", self._device.address)
                await self.disconnect()
                return False

            self._paired = True
            _LOGGER.info(
                "Successfully paired with WaterGenius device %s",
                self._device.address,
            )

            # Subscribe to notifications
            await self._subscribe_notifications()

            return True

        except Exception:
            _LOGGER.exception("Failed to connect to %s", self._device.address)
            await self.disconnect()
            return False

    async def _pair(self) -> bool:
        """Perform Telink mesh pairing (session key exchange).

        1. Generate 8-byte random nonce
        2. Write pair request to pair characteristic
        3. Read response with device nonce
        4. Derive session key
        """
        if not self._client:
            return False

        session_random = os.urandom(8)

        # Build and send pair request
        pair_packet = _make_pair_packet(
            self._mesh_name, self._mesh_password, session_random
        )
        _LOGGER.debug("Writing pair request (%d bytes)", len(pair_packet))
        await self._client.write_gatt_char(
            PAIR_UUID, bytes(pair_packet), response=True
        )

        await asyncio.sleep(0.5)

        # Read response
        response = await self._client.read_gatt_char(PAIR_UUID)
        _LOGGER.debug("Pair response: %s", bytes(response).hex())

        if not response or len(response) < 1:
            _LOGGER.error("Empty pair response")
            return False

        # Check response code
        if response[0] == 0x0E:
            _LOGGER.error(
                "Pair authentication failed (wrong mesh name/password)"
            )
            return False

        if response[0] != 0x0D:
            _LOGGER.error("Unexpected pair response code: 0x%02X", response[0])
            return False

        # Extract device nonce (bytes 1-8)
        response_random = bytes(response[1:9])

        # Derive session key
        self._session_key = _make_session_key(
            self._mesh_name, self._mesh_password, session_random, response_random
        )
        _LOGGER.debug("Session key derived successfully")

        # Enable notifications by writing 0x01 to the status characteristic
        await self._client.write_gatt_char(
            NOTIFY_UUID, b"\x01", response=True
        )

        return True

    async def _subscribe_notifications(self) -> None:
        """Subscribe to the notify characteristic for incoming data."""
        if not self._client:
            return

        def _handle_notification(_sender: int, data: bytearray) -> None:
            if self._session_key is None:
                return

            decrypted = _decrypt_notification(
                bytes(self._session_key),
                self._device.address,
                bytes(data),
            )

            if decrypted is None:
                _LOGGER.debug("Failed to decrypt notification")
                return

            _LOGGER.debug("Notification (decrypted): %s", decrypted.hex())

            if self._notification_callback:
                self._notification_callback(decrypted)

        await self._client.start_notify(NOTIFY_UUID, _handle_notification)
        _LOGGER.debug("Subscribed to notifications")

    async def send_command(
        self, opcode: int, data: bytes = b"", dest_id: int = 0xFFFF
    ) -> None:
        """Send an encrypted command to the device.

        Args:
            opcode: Telink mesh command opcode.
            data: Command parameters.
            dest_id: Destination mesh ID (0xFFFF for broadcast).
        """
        if not self._client or not self._session_key:
            _LOGGER.error("Cannot send command: not connected/paired")
            return

        packet = _make_command_packet(
            bytes(self._session_key),
            self._device.address,
            dest_id,
            opcode,
            data,
        )

        await self._client.write_gatt_char(
            COMMAND_UUID, bytes(packet), response=False
        )
        _LOGGER.debug(
            "Sent command opcode=0x%02X data=%s dest=0x%04X",
            opcode,
            data.hex(),
            dest_id,
        )

    async def request_status(self) -> None:
        """Request the device to send its current status.

        Uses opcode 0xDA (status query) or vendor-specific Gizwits opcodes.
        The device should respond via notification with status data.
        """
        # Try standard Telink status query first
        await self.send_command(0xDA, b"")

        # Also try vendor-specific status request (Gizwits uses 0xEA for user commands)
        await asyncio.sleep(0.3)
        await self.send_command(0xEA, b"\x01")

    async def write_data_point(
        self, dp_name: str, value: int
    ) -> None:
        """Write a value to a writable data point.

        Uses Gizwits vendor command (opcode 0xEA) to set a data point value.
        """
        from .gizwits_protocol import DATA_POINTS, number2bytes

        dp = DATA_POINTS.get(dp_name)
        if dp is None:
            _LOGGER.error("Unknown data point: %s", dp_name)
            return
        if not dp.writable:
            _LOGGER.error("Data point %s is not writable", dp_name)
            return

        value_bytes = number2bytes(value, dp.byte_length)
        # Vendor-specific write via opcode 0xEA
        await self.send_command(0xEA, bytes([0x02]) + value_bytes)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        self._paired = False
        self._connected = False
        self._session_key = None
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                _LOGGER.debug("Error during disconnect", exc_info=True)
            self._client = None
