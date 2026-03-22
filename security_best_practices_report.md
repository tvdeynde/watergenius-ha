# WaterGenius Security Review

## Executive Summary

This Home Assistant integration has no obvious cloud-exposure or command-injection issues, but it does trust nearby BLE devices and raw BLE traffic too broadly. The highest-risk issue is an unbounded notification reassembly buffer that a spoofed or malicious local BLE device can use to consume memory and destabilize Home Assistant. I also found weak device identity validation and verbose logging of sensitive household telemetry.

## Critical / High

### WG-001: Unbounded BLE packet buffering allows local memory exhaustion

**Impact:** A nearby BLE device that the integration connects to can stream 128-byte notifications forever and cause unbounded memory growth inside Home Assistant.

- File: `custom_components/watergenius/gizwits_ble.py`
- Lines: 151-172, 174-192

`_handle_notification()` appends every packet into `self._receive_buffer` and only flushes when it sees a short packet or a timeout. There is no maximum frame size, no sanity check against the expected dump size, and no reset when the buffer exceeds plausible protocol limits. A malicious device can keep sending full-size packets more frequently than `_PACKET_GROUP_TIMEOUT`, preventing the timeout flush and growing the buffer indefinitely.

Because the integration exposes Bluetooth discovery and manual pairing, this is a realistic local attacker/rogue-device denial-of-service path. The fix is to cap the reassembly buffer to a strict protocol maximum, drop oversize frames, and disconnect or ignore the device after repeated malformed dumps.

## Medium

### WG-002: Device identity verification is too weak, enabling BLE spoofing and data poisoning

- Files: `custom_components/watergenius/config_flow.py`, `custom_components/watergenius/__init__.py`, `custom_components/watergenius/gizwits_ble.py`
- Lines: `custom_components/watergenius/config_flow.py` 29-56, 135-151; `custom_components/watergenius/__init__.py` 30-50; `custom_components/watergenius/gizwits_ble.py` 93-123

The integration accepts devices as potential WaterGenius hardware if they match only one broad signal: the service UUID, a name prefix, or a manufacturer payload substring. The Bluetooth discovery step then creates an entry immediately from the discovered address, and the BLE connection code chooses the first notify/write characteristic it finds on the device instead of enforcing the expected UUIDs.

In practice, a nearby BLE device can impersonate a compatible advertiser, get paired, feed arbitrary telemetry into Home Assistant, and receive future control traffic once command support is implemented. This is a local-network/radio-range issue, not an internet issue, but it is still an authentication weakness at the trust boundary.

Mitigations:
- Require stronger matching before creating an entry, ideally combining service UUID with expected manufacturer data/product key.
- Re-validate identity during connect before trusting notifications.
- Pin communication to the known WaterGenius characteristic UUIDs instead of selecting the first writable/notifiable characteristic on the device.

### WG-003: Logs expose sensitive telemetry and raw BLE payloads

- Files: `custom_components/watergenius/coordinator.py`, `custom_components/watergenius/gizwits_ble.py`
- Lines: `custom_components/watergenius/coordinator.py` 103, 126-148, 157-164; `custom_components/watergenius/gizwits_ble.py` 73-77, 113-123, 142-144, 186-189, 221

The integration logs full BLE frames, parsed sensor values, connection metadata, and command payloads. Even though some of this is at `debug`, several parsed values and raw periodic-update bytes are logged at `info`. Those values reveal water consumption, regeneration timing, salt level, device address, and other household-behavior signals that are sensitive in Home Assistant environments.

This is primarily a confidentiality/privacy issue if logs are shared for support, forwarded to external log sinks, or accessible to other administrators. Logging should be reduced to coarse operational events by default, and raw payloads or detailed telemetry should be removed or gated behind explicit debug diagnostics with redaction where possible.

## Low / Hardening

### WG-004: Manual address entry accepts non-hex identifiers

- File: `custom_components/watergenius/config_flow.py`
- Lines: 111-120

Manual device entry checks only that the normalized address is 12 characters long. It does not ensure the value is hexadecimal. This is not a serious vulnerability by itself, but stricter validation would reduce malformed config entries and make spoofing/mistakes slightly harder.

## Notes

- I did not find any network listeners, remote-code-execution primitives, shell execution, or secret-handling logic in this repository.
- I did not run runtime BLE tests; this review is based on static analysis of the checked-in code.
