# WaterGenius Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration for **WaterGenius water softener** devices. Connects directly over **Bluetooth Low Energy (BLE)** to read sensor data and control your water softener — no cloud, no internet required.

## Features

- **Automatic BLE discovery** — WaterGenius devices (advertising as `XPG-GAgent-xxxx`) are detected automatically
- **20+ sensor entities** — water hardness, flow rate, capacity, salt level, regeneration status, water usage, and more
- **2 binary sensors** — alarm status and regeneration activity
- **2 action buttons** — trigger immediate or scheduled regeneration
- **1 switch** — toggle salt alarm sound
- **No cloud dependency** — communicates directly with the device over Bluetooth
- **Official data point schema** — byte offsets sourced from the Gizwits product API (218 data points)

## Requirements

- Home Assistant 2024.1 or newer
- A Bluetooth adapter on your Home Assistant host (built-in or USB)
- The WaterGenius device must be within Bluetooth range (~10m) of the HA host
- **Important:** Only one BLE client can connect to the device at a time. Close the WaterGenius phone app before the integration connects.

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
3. Select your device from the list — it appears as `XPG-GAgent-xxxx`
4. If not listed, choose **"Enter address manually..."** and type the Bluetooth MAC address
5. The integration creates a device with all entities

If no devices are found:
- Make sure the WaterGenius phone app is fully closed (BLE allows only one connection)
- Verify your HA host has a working Bluetooth adapter
- Ensure the device is powered on and within Bluetooth range

### Finding the MAC address

- Check the WaterGenius phone app (device info/settings)
- Look in your phone's Bluetooth settings while connected to the device
- The device advertises as `XPG-GAgent-xxxx` where `xxxx` is the last 4 characters of the MAC

## Entities

### Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| Incoming Hardness | Water hardness before softening | mg/L |
| Outgoing Hardness | Water hardness after softening | mg/L |
| Hardness Unit | Active hardness unit (mg/L, °dH, °fH, etc.) | — |
| Current Flow Rate | Real-time water flow | L/min |
| Remaining Capacity | Remaining softening capacity before regeneration | L |
| Remaining Capacity % | Remaining capacity as percentage | % |
| Total Capacity | Total softening capacity | L |
| Salt Level | Current salt level in the brine tank | % |
| Days to Next Regeneration | Estimated days until next regeneration cycle | days |
| Average Daily Water Usage | Average daily water consumption | L |
| Today Water Usage | Water used today | L |
| Total Water Usage | Cumulative water usage since installation | L |
| Total Hardness Removal | Cumulative hardness removed since installation | mg CaCO₃ |
| Valve State | Current valve position (In Service, Brine, Backwash, Rinse, Refill) | — |
| Regeneration Countdown | Time remaining in current regeneration phase | seconds |
| Peak Flow Rate | Highest recorded flow rate | — |
| Total Regeneration Count | Total number of regeneration cycles | — |
| Error Log | Device error code | — |

### Binary Sensors

| Entity | Description | Device Class |
|--------|-------------|--------------|
| Alarm | Active when the device has an alarm condition (e.g. low salt) | Problem |
| Regenerating | Active during a regeneration cycle | Running |

### Controls

| Entity | Type | Description |
|--------|------|-------------|
| Immediate Proportional Regeneration | Button | Triggers an immediate partial regeneration |
| Full Regeneration Tonight | Button | Schedules a full regeneration for tonight |
| Salt Alarm Sound | Switch | Toggle the audible salt level alarm |

## How It Works

### Protocol Stack

```
┌─────────────────────────────────┐
│   Gizwits Data Points           │  ← 218 named data points with known byte offsets
├─────────────────────────────────┤
│   Proprietary Binary Protocol   │  ← 38-byte header + 807-byte payload over BLE
├─────────────────────────────────┤
│   Bluetooth Low Energy (BLE)    │  ← Service 0xABF0, characteristic 0xABF7
└─────────────────────────────────┘
```

### BLE Details

| Item | Value |
|---|---|
| Service UUID | `0000ABF0-0000-1000-8000-00805F9B34FB` |
| Characteristic UUID | `0000ABF7-...` (single characteristic for read/write/notify) |
| Manufacturer ID | `0x1910` (Gizwits) |
| Device name pattern | `XPG-GAgent-xxxx` |
| Protocol | Proprietary binary dump (unencrypted) |

### Connection Flow

1. **Discovery** — HA detects the device by service UUID (`0xABF0`) or name (`XPG-GAgent-xxxx`)
2. **Connect** — Standard BLE GATT connection (no encryption or pairing needed)
3. **Subscribe** — Enable notifications on characteristic `0xABF7`
4. **Receive** — Device sends a `0xFFFF` handshake, then a full data dump (~845 bytes) split across multiple 128-byte BLE packets approximately 8 seconds after connection
5. **Poll** — Periodic status updates (~42 bytes) arrive every ~7 seconds; full status re-requested every 60 seconds

### Data Format

The device sends its complete state as a raw binary dump:
- **38-byte header** — device metadata
- **807-byte Gizwits payload** — all 218 data points packed sequentially per the [Gizwits product schema](https://docs.gizwits.com/)

Data point byte offsets were obtained from the official Gizwits API using the device's product key. Values are big-endian encoded.

### Reverse Engineering

This integration was built by reverse-engineering the WaterGenius Android APK (v1.0.27):

1. **APK analysis** — Extracted the React Native JavaScript bundle to find data point names (`g_uiHardness`, `g_ucRegenStatus`, etc.) and the Gizwits product key
2. **BLE discovery** — Identified the device as a Gizwits GAgent (`XPG-GAgent`) using service UUID `0xABF0` and manufacturer ID `0x1910`
3. **Characteristic discovery** — Found the device uses a single characteristic `0xABF7` (not the standard `ABF1`/`ABF2` split)
4. **Protocol analysis** — Determined the device sends raw binary dumps (not standard Gizwits serial framing)
5. **Schema mapping** — Fetched the official 218-data-point product schema from the Gizwits API to get exact byte offsets and lengths

## Troubleshooting

### Device not found
- Ensure the WaterGenius phone app is fully closed (it holds an exclusive BLE connection)
- Check that your HA host has a working Bluetooth adapter
- Move the HA host closer to the device (BLE range is ~10m)
- Use the manual MAC address entry option if the device doesn't appear in the list

### Sensors show "Unknown"
- Some sensors (Valve State, Regenerating) only populate after a full data dump is received, which takes ~10 seconds after connection
- If sensors stay "Unknown", check HA logs for connection errors
- Try removing and re-adding the integration

### Connection drops
- Only one BLE client can connect at a time — close the phone app
- Try power-cycling the WaterGenius device
- Check that no other Bluetooth integration is holding a connection

### Enable debug logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.watergenius: debug
```

This logs raw BLE packets and parsed data point values.

## Known Limitations

- **Control commands** (regeneration buttons, salt alarm switch) are defined but the exact write protocol for this device's proprietary format has not yet been validated
- **Concurrent access** — the phone app and HA cannot connect simultaneously; close the app before HA connects
- **BLE range** — requires the HA host to be within ~10m of the water softener

## License

This project is provided as-is for personal use. Not affiliated with or endorsed by WaterGenius or Gizwits.

## Credits

- Data point schema from [Gizwits IoT Platform](https://www.gizwits.com/)
- Protocol analysis referenced [Gizwits GAgent source](https://github.com/gizwits/Gizwits-GAgent)
- Built for [Home Assistant](https://www.home-assistant.io/)
