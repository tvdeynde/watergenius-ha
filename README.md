# WaterGenius Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration for **WaterGenius water softener** devices. Connects directly over **Bluetooth Low Energy (BLE)** using the Telink mesh protocol to read sensor data and control your water softener.

## Features

- **Automatic BLE discovery** — WaterGenius devices are detected automatically when in Bluetooth range
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
3. Select your device from the list of discovered Bluetooth devices
4. Confirm the mesh credentials (defaults work for most devices)
5. The integration will create a device with all entities

If no devices are found, make sure:
- The device is powered on
- The WaterGenius phone app is closed (BLE allows only one connection)
- Your HA host has a working Bluetooth adapter
- The device is within Bluetooth range

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

The WaterGenius device communicates using a layered protocol:

```
┌─────────────────────────────────┐
│   Gizwits Data Points           │  ← Named data points (hardness, flow, etc.)
├─────────────────────────────────┤
│   Telink Mesh Protocol          │  ← AES-128 encrypted mesh commands
├─────────────────────────────────┤
│   Bluetooth Low Energy (BLE)    │  ← Physical transport (bleak library)
└─────────────────────────────────┘
```

### BLE Characteristics

| Characteristic | UUID | Purpose |
|---|---|---|
| Service | `00010203-0405-0607-0809-0a0b0c0d1910` | Main mesh service |
| Notify | `...1911` | Receive status updates from device |
| Command | `...1912` | Send commands to device |
| Pair | `...1914` | Session key exchange during pairing |

### Connection Flow

1. **Discovery** — HA's Bluetooth integration detects the device by its service UUID
2. **Pairing** — AES-128 session key exchange using mesh name and password
3. **Subscription** — Subscribe to BLE notifications for real-time data updates
4. **Polling** — Periodic status requests every 60 seconds as a safety net

### Reverse Engineering

This integration was built by reverse-engineering the WaterGenius Android APK (v1.0.27). The app is built with React Native on the [Gizwits IoT platform](https://www.gizwits.com/). Key findings:

- The JavaScript bundle contains all data point definitions (`g_uiHardness`, `g_ucRegenStatus`, etc.)
- BLE communication uses the Telink mesh protocol with default mesh credentials
- Data points use big-endian byte encoding (the `bytes2number` / `number2bytes` pattern from the APK)
- The Telink mesh encryption follows the standard protocol documented in [google/python-dimond](https://github.com/google/python-dimond) and [Leiaz/python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light)

## Troubleshooting

### Device not found
- Ensure the WaterGenius phone app is fully closed (it holds an exclusive BLE connection)
- Check that your HA host has a working Bluetooth adapter (`bluetoothctl list`)
- Move the HA host closer to the device (BLE range is ~10m)
- Check Home Assistant logs for Bluetooth adapter errors

### Pairing fails
- The default mesh credentials (`telink_mesh1` / `123`) work for most devices
- If your device has custom mesh settings, enter them during configuration
- Try power-cycling the WaterGenius device

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

This will log raw BLE packets and parsed data point values, which is helpful for diagnosing protocol issues.

## Development Status

This integration is in **early development**. The Telink mesh protocol and BLE pairing are well-understood and based on proven open-source implementations. However, the **Gizwits data point encoding over BLE** (the exact byte layout in status notifications) is based on APK analysis and may need adjustment when tested against real hardware.

Areas that may need refinement:
- Data point byte order and offsets in BLE notification payloads
- Vendor-specific command opcodes for Gizwits data point read/write
- Handling of array data points (daily/weekly/monthly usage)
- BLE reconnection reliability

Contributions and bug reports are welcome!

## License

This project is provided as-is for personal use. Not affiliated with or endorsed by WaterGenius or Gizwits.

## Credits

- Protocol analysis based on [google/python-dimond](https://github.com/google/python-dimond), [Leiaz/python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light), and [vpaeder/telinkpp](https://github.com/vpaeder/telinkpp)
- Built for [Home Assistant](https://www.home-assistant.io/)
