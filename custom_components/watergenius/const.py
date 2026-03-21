"""Constants for the WaterGenius integration."""

from __future__ import annotations

DOMAIN = "watergenius"
MANUFACTURER = "WaterGenius"

# BLE Service and Characteristic UUIDs (Telink Mesh)
SERVICE_UUID = "00010203-0405-0607-0809-0a0b0c0d1910"
PAIR_UUID = "00010203-0405-0607-0809-0a0b0c0d1914"
COMMAND_UUID = "00010203-0405-0607-0809-0a0b0c0d1912"
NOTIFY_UUID = "00010203-0405-0607-0809-0a0b0c0d1911"

# Default Telink Mesh credentials (from APK)
DEFAULT_MESH_NAME = "telink_mesh1"
DEFAULT_MESH_PASSWORD = "123"
DEFAULT_MESH_LTK = bytes.fromhex("c0c1c2c3c4c5c6c7d8d9dadbdcdddedf")
DEFAULT_MESH_VENDOR = 1

# Gizwits Product Keys
PRODUCT_KEYS = [
    "1462685633a0472ea32994c3d33b40d8",
    "1952e24ea3744832aa55cf9a5050fc6d",
]

# Config flow keys
CONF_MESH_NAME = "mesh_name"
CONF_MESH_PASSWORD = "mesh_password"
CONF_MESH_LTK = "mesh_ltk"
CONF_DEVICE_ADDRESS = "device_address"

# Polling interval
DEFAULT_SCAN_INTERVAL = 60  # seconds

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
