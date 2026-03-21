# WaterGenius Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration for **WaterGenius water softener** devices. Connects directly over **Bluetooth Low Energy (BLE)** using the Gizwits GAgent protocol to read sensor data and control your water softener.

## Features

- **Automatic BLE discovery** — WaterGenius devices (advertising as `XPG-GAgent-xxxx`) are detected automatically when in Bluetooth range
- **17 sensor entities** — water hardness (in/out), flow rate, remaining capacity, salt level, regeneration status, water usage statistics, and more
- **2 binary sensors** — alarm status and regeneration activity
- **2 action buttons** — trigger immediate or scheduled regeneration
- **1 switch** — toggle salt alarm sound
- **No cloud dependency** — communicates directly with the device over Bluetooth

## Requirements

- Home Assistant 2024.1 or newer
- A Bluetooth adapter on your Home Assistant host (built-in or USB)
- The WaterGenius device must be within Bluetooth range (~10m) of the HA host
- **Important:** Only one BLE central can connect to the device at a time. Close the WaterGenius phone app before the integration connects.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu (top right) → **Custom repositories**
3. Add `https://github.com/tvdeynde/watergenius-ha` with category **Integration**
4. Search for "WaterGenius" and install
5. Restart Home Assistant

### Manual

1. Download or clone this repository
2. Copy the `custom_components/watergenius` folder into your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **WaterGenius**
3. Select your device from the list of discovered Bluetooth devices — it will appear as `XPG-GAgent-xxxx`
4. If your device is not listed, choose **"Enter address manually..."** and enter the Bluetooth MAC address
5. The integration will create a device with all entities

If no devices are found, make sure:
- The device is powered on
- The WaterGenius phone app is fully closed (BLE allows only one connection at a time)
- Your HA host has a working Bluetooth adapter
- The device is within Bluetooth range

### Finding the MAC address

If you need to enter the address manually:
- Check the WaterGenius phone app (device info/settings)
- Look in your phone's Bluetooth settings while connected to the device
- The device advertises as `XPG-GAgent-xxxx` where `xxxx` is the last 4 characters of the MAC

## Entities

### Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| Incoming Hardness | Water hardness before softening | Depends on device setting |
| Outgoing Hardness | Water hardness after softening | Depends on device setting |
| Hardness Unit | Active hardness unit (mg/L, °dH, °fH, etc.) | — |
| Current Flow Rate | Real-time water flow | L/min |
| Remaining Capacity | Remaining softening capacity before regeneration | L |
| Salt Level | Current salt level in the brine tank | % |
| Days to Next Regeneration | Estimated days until next regeneration cycle | days |
| Average Daily Water Usage | Average daily water consumption | L |
| Total Hardness Removal | Cumulative hardness removed since installation | mg CaCO₃ |
| Regeneration Flow Setting | Configured regeneration flow volume | L |
| Valve State | Current valve position (In Service, Brine, Backwash, Rinse, Refill) | — |
| Regeneration Countdown | Time remaining in current regeneration phase | seconds |
| Regeneration Time | Configured regeneration start time | HH:MM |
| Alarm On Time | Configured alarm on time | HH:MM |
| Alarm Off Time | Configured alarm off time | HH:MM |
| Daily Water Usage Detail | Average usage with detailed breakdown in attributes | L |
| Error Log | Device error code | — |

The **Daily Water Usage Detail** sensor includes extra attributes with historical data:
- `usage_2h_slots` — water usage per 2-hour interval (12 values for 24h)
- `weekly_flow_avg` — average flow per day of the week (7 values)
- `monthly_flow_avg` — average flow per month (4 values)
- `weekly_water_usage` — total usage per day of the week (7 values)

### Binary Sensors

| Entity | Description | Device Class |
|--------|-------------|--------------|
| Alarm | Active when the device has an alarm condition | Problem |
| Regenerating | Active during a regeneration cycle | Running |

### Buttons

| Entity | Description |
|--------|-------------|
| Immediate Proportional Regeneration | Triggers an immediate partial regeneration |
| Full Regeneration Tonight | Schedules a full regeneration for tonight |

### Switches

| Entity | Description |
|--------|-------------|
| Salt Alarm Sound | Toggle the audible salt level alarm |

## How It Works

### Protocol Stack

The WaterGenius device communicates using the Gizwits GAgent BLE protocol:

```
┌─────────────────────────────────┐
│   Gizwits Data Points           │  ← Named data points (hardness, flow, etc.)
├─────────────────────────────────┤
│   Gizwits GAgent Protocol       │  ← Framed serial protocol over BLE SPP
├─────────────────────────────────┤
│   Bluetooth Low Energy (BLE)    │  ← Physical transport (bleak library)
└─────────────────────────────────┘
```

### BLE Service and Characteristics

The device uses the Gizwits BLE SPP (Serial Port Profile) service:

| Characteristic | UUID | Purpose |
|---|---|---|
| Service | `0000ABF0-0000-1000-8000-00805F9B34FB` | Gizwits BLE SPP service |
| Write | `0000ABF1-...` | Send commands to device |
| Notify | `0000ABF2-...` | Receive status updates from device |

### Protocol Framing

Each packet uses this format:

```
| header (0xFFFF) | length (2B) | cmd (1B) | sn (1B) | flags (2B) | payload (NB) | checksum (1B) |
```

Key commands:
- `0x03` — Control (write data points)
- `0x05` — Status report (device sends all data points)
- `0x07` / `0x08` — Heartbeat ping/ACK

The protocol is **unencrypted** — no pairing or authentication is needed beyond the BLE connection itself.

### Connection Flow

1. **Discovery** — HA detects the device by its service UUID (`0xABF0`) or name (`XPG-GAgent-xxxx`)
2. **Connect** — Standard BLE GATT connection (no encryption or pairing needed)
3. **Subscribe** — Enable notifications on characteristic `0xABF2`
4. **Heartbeat** — Send a ping to verify communication
5. **Poll** — Request status every 60 seconds; device also pushes updates via notifications

### Reverse Engineering

This integration was built by reverse-engineering the WaterGenius Android APK (v1.0.27). The app is built with React Native on the [Gizwits IoT platform](https://www.gizwits.com/). Key findings:

- The device advertises as `XPG-GAgent-xxxx` with Gizwits manufacturer ID `0x1910`
- BLE advertisement data contains the product key (`1952e24ea3744832aa55cf9a5050fc6d`)
- The JavaScript bundle contains all data point definitions (`g_uiHardness`, `g_ucRegenStatus`, etc.)
- Data points use big-endian byte encoding
- Communication uses the Gizwits GAgent serial protocol over BLE SPP (service `0xABF0`)

## Troubleshooting

### Device not found
- Ensure the WaterGenius phone app is fully closed (it holds an exclusive BLE connection)
- Check that your HA host has a working Bluetooth adapter (`bluetoothctl list`)
- Move the HA host closer to the device (BLE range is ~10m)
- Check Home Assistant logs for Bluetooth adapter errors
- Use the manual address entry option if the device doesn't appear in the list

### Connection fails
- Only one BLE client can connect at a time — make sure the phone app is closed
- Try power-cycling the WaterGenius device
- Check that no other Bluetooth integration is holding a connection to the device

### Sensors show "Unknown" or "Unavailable"
- The data point byte layout may need adjustment for your specific device firmware version
- Check HA logs (`Logger: custom_components.watergenius`) for raw notification data
- Open an issue with the log output for debugging

### Enable debug logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.watergenius: debug
```

This will log raw BLE packets, parsed protocol frames, and data point values — very helpful for diagnosing issues.

## Development Status

This integration is in **early development**. The Gizwits GAgent BLE protocol is well-understood based on the [Gizwits GAgent source code](https://github.com/gizwits/Gizwits-GAgent). However, the **data point byte layout** in status reports is based on APK analysis and may need adjustment when tested against real hardware.

Areas that may need refinement:
- Data point byte order and offsets in status report payloads
- Control command encoding (attr_flags and attr_vals format)
- Handling of array data points (daily/weekly/monthly usage)
- BLE reconnection reliability

Contributions and bug reports are welcome!

## License

This project is provided as-is for personal use. Not affiliated with or endorsed by WaterGenius or Gizwits.

## Credits

- Protocol based on [Gizwits GAgent](https://github.com/gizwits/Gizwits-GAgent) and [Gizwits documentation](https://docs.gizwits.com/)
- Built for [Home Assistant](https://www.home-assistant.io/)
