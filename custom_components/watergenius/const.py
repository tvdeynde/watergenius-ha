"""Constants for the WaterGenius integration."""

from __future__ import annotations

DOMAIN = "watergenius"
MANUFACTURER = "WaterGenius"

# BLE Service and Characteristic UUIDs (Gizwits GAgent BLE SPP)
SERVICE_UUID = "0000abf0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000abf1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000abf2-0000-1000-8000-00805f9b34fb"

# Gizwits manufacturer ID in BLE advertisements
GIZWITS_MANUFACTURER_ID = 0x1910

# Gizwits Product Keys (from APK)
PRODUCT_KEYS = [
    "1462685633a0472ea32994c3d33b40d8",
    "1952e24ea3744832aa55cf9a5050fc6d",
]

# Config flow keys
CONF_DEVICE_ADDRESS = "device_address"

# Polling interval
DEFAULT_SCAN_INTERVAL = 60  # seconds

# Gizwits protocol constants
GIZWITS_HEADER = b"\xFF\xFF"

# Command types
CMD_MCU_INFO = 0x01
CMD_MCU_INFO_ACK = 0x02
CMD_CTRL = 0x03
CMD_CTRL_ACK = 0x04
CMD_REPORT = 0x05
CMD_REPORT_ACK = 0x06
CMD_HEARTBEAT = 0x07
CMD_HEARTBEAT_ACK = 0x08

# P0 action types
ACTION_CONTROL = 0x01
ACTION_READ_STATUS = 0x02
ACTION_READ_STATUS_ACK = 0x03
ACTION_REPORT_STATUS = 0x04

# Hardness units
HARDNESS_UNITS = {
    0: "mg/L",
    1: "gpG",
    2: "°dH",
    3: "°eH",
    4: "°fH",
    5: "mmol/l CaCO₃",
}

# Valve / regeneration states
VALVE_STATES = {
    0: "In Service",
    1: "Brine",
    2: "Backwash",
    3: "Rinse",
    5: "Refill",
}
