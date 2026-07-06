"""Gizwits data point encoding/decoding for WaterGenius devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class DataPointType(IntEnum):
    """Data point types."""

    BOOL = 0
    ENUM = 1
    NUMBER = 2
    BYTES = 3


@dataclass
class DataPointDef:
    """Definition of a Gizwits data point."""

    name: str
    dp_type: DataPointType
    byte_length: int
    writable: bool = False
    description: str = ""


# Data point definitions derived from the APK reverse engineering.
# The exact byte offsets in the BLE status payload need validation
# against a real device. These definitions capture the logical data model.
DATA_POINTS: dict[str, DataPointDef] = {
    # Read-only status data points (g_ prefix in APK)
    "g_uiHardness": DataPointDef(
        name="g_uiHardness",
        dp_type=DataPointType.NUMBER,
        byte_length=2,
        description="Incoming water hardness",
    ),
    "g_uiHardnessOut": DataPointDef(
        name="g_uiHardnessOut",
        dp_type=DataPointType.NUMBER,
        byte_length=2,
        description="Outgoing water hardness",
    ),
    "g_ucWaterHdUintSetUSER": DataPointDef(
        name="g_ucWaterHdUintSetUSER",
        dp_type=DataPointType.ENUM,
        byte_length=1,
        description="Water hardness unit",
    ),
    "g_ucRegenStatus": DataPointDef(
        name="g_ucRegenStatus",
        dp_type=DataPointType.BYTES,
        byte_length=2,
        description="Regeneration status (byte0=valve state, byte1=countdown)",
    ),
    "g_ulFlowCurrent": DataPointDef(
        name="g_ulFlowCurrent",
        dp_type=DataPointType.NUMBER,
        byte_length=4,
        description="Current flow rate",
    ),
    "g_ulRemainCap": DataPointDef(
        name="g_ulRemainCap",
        dp_type=DataPointType.NUMBER,
        byte_length=4,
        description="Remaining capacity",
    ),
    "g_ulRegenFlowSet": DataPointDef(
        name="g_ulRegenFlowSet",
        dp_type=DataPointType.NUMBER,
        byte_length=4,
        description="Regeneration flow setting",
    ),
    "g_ucCaCO3Total": DataPointDef(
        name="g_ucCaCO3Total",
        dp_type=DataPointType.NUMBER,
        byte_length=4,
        description="Total hardness removal (CaCO3)",
    ),
    "g_ucCurrentSaltLevel": DataPointDef(
        name="g_ucCurrentSaltLevel",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Current salt level",
    ),
    "g_usEstDaysToNext": DataPointDef(
        name="g_usEstDaysToNext",
        dp_type=DataPointType.NUMBER,
        byte_length=2,
        description="Estimated days to next regeneration",
    ),
    "g_uiDailyWaterUsageAvg": DataPointDef(
        name="g_uiDailyWaterUsageAvg",
        dp_type=DataPointType.NUMBER,
        byte_length=2,
        description="Average daily water usage",
    ),
    "g_uiDailyWaterUsage2H_12": DataPointDef(
        name="g_uiDailyWaterUsage2H_12",
        dp_type=DataPointType.BYTES,
        byte_length=24,  # 12 x 2 bytes
        description="Daily water usage in 2h intervals (12 values)",
    ),
    "g_uiWeekFlowAvg_7": DataPointDef(
        name="g_uiWeekFlowAvg_7",
        dp_type=DataPointType.BYTES,
        byte_length=14,  # 7 x 2 bytes
        description="Weekly flow averages (7 values)",
    ),
    "g_uiMonthFlowAvg_4": DataPointDef(
        name="g_uiMonthFlowAvg_4",
        dp_type=DataPointType.BYTES,
        byte_length=8,  # 4 x 2 bytes
        description="Monthly flow averages (4 values)",
    ),
    "g_uiWeekWaterUsage1_7": DataPointDef(
        name="g_uiWeekWaterUsage1_7",
        dp_type=DataPointType.BYTES,
        byte_length=14,  # 7 x 2 bytes
        description="Weekly water usage (7 values)",
    ),
    "g_ucWeekRegenFlag": DataPointDef(
        name="g_ucWeekRegenFlag",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Weekly regeneration flags",
    ),
    "g_ucAlarm": DataPointDef(
        name="g_ucAlarm",
        dp_type=DataPointType.BOOL,
        byte_length=1,
        description="Alarm status",
    ),
    "g_ucRegenEN": DataPointDef(
        name="g_ucRegenEN",
        dp_type=DataPointType.BOOL,
        byte_length=1,
        description="Regeneration enabled",
    ),
    "g_ucAlarmOnHour": DataPointDef(
        name="g_ucAlarmOnHour",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Alarm on hour",
    ),
    "g_ucAlarmOnMin": DataPointDef(
        name="g_ucAlarmOnMin",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Alarm on minute",
    ),
    "g_ucAlarmOffHour": DataPointDef(
        name="g_ucAlarmOffHour",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Alarm off hour",
    ),
    "g_ucAlarmOffMin": DataPointDef(
        name="g_ucAlarmOffMin",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Alarm off minute",
    ),
    "g_uiRegenTimeHourMin": DataPointDef(
        name="g_uiRegenTimeHourMin",
        dp_type=DataPointType.NUMBER,
        byte_length=2,
        description="Regeneration time (hour*100+min)",
    ),
    "g_ucHolidayYear": DataPointDef(
        name="g_ucHolidayYear",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Holiday mode year",
    ),
    "g_ucHolidayMon": DataPointDef(
        name="g_ucHolidayMon",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Holiday mode month",
    ),
    "g_ucHolidayDay": DataPointDef(
        name="g_ucHolidayDay",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Holiday mode day",
    ),
    "g_ulERRLog0": DataPointDef(
        name="g_ulERRLog0",
        dp_type=DataPointType.NUMBER,
        byte_length=4,
        description="Error log",
    ),
    "g_ucL1Reserved1": DataPointDef(
        name="g_ucL1Reserved1",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        description="Reserved",
    ),
    # Writable control data points (f_ prefix in APK)
    "f_ucRegenDelay": DataPointDef(
        name="f_ucRegenDelay",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        writable=True,
        description="Trigger regeneration",
    ),
    "f_ucTipsSoundSet": DataPointDef(
        name="f_ucTipsSoundSet",
        dp_type=DataPointType.BOOL,
        byte_length=1,
        writable=True,
        description="Salt alarm sound on/off",
    ),
    "f_ucRegenModeSetHoliday": DataPointDef(
        name="f_ucRegenModeSetHoliday",
        dp_type=DataPointType.NUMBER,
        byte_length=1,
        writable=True,
        description="Holiday mode setting",
    ),
    "f_ucSysTime": DataPointDef(
        name="f_ucSysTime",
        dp_type=DataPointType.BYTES,
        byte_length=6,
        writable=True,
        description="System time",
    ),
}


def bytes2number(data: bytes | list[int]) -> int:
    """Convert byte array to number (big-endian).

    Matches the APK's bytes2number: concatenates bytes as hex and parses as int.
    E.g. [0x01, 0xF4] -> 0x01f4 -> 500
    """
    if not data:
        return 0
    return int.from_bytes(bytes(data), byteorder="big")


def number2bytes(value: int, length: int) -> bytes:
    """Convert number to byte array (big-endian).

    Matches the APK's number2bytes.
    E.g. 500, 2 -> [0x01, 0xF4]
    """
    return value.to_bytes(length, byteorder="big")


def parse_array_data(data: bytes, element_size: int) -> list[int]:
    """Parse an array of numbers from a byte buffer.

    Used for data points like g_uiDailyWaterUsage2H_12 (12 x 2-byte values).
    """
    result = []
    for i in range(0, len(data), element_size):
        chunk = data[i : i + element_size]
        if len(chunk) == element_size:
            result.append(bytes2number(chunk))
    return result


@dataclass
class WaterGeniusDeviceData:
    """Parsed device data from BLE notifications."""

    raw: dict[str, bytes] = field(default_factory=dict)

    def get_number(self, dp_name: str) -> int | None:
        """Get a numeric data point value."""
        if dp_name not in self.raw:
            return None
        return bytes2number(self.raw[dp_name])

    def get_bool(self, dp_name: str) -> bool | None:
        """Get a boolean data point value."""
        if dp_name not in self.raw:
            return None
        return bytes2number(self.raw[dp_name]) != 0

    def get_bytes(self, dp_name: str) -> bytes | None:
        """Get raw bytes for a data point."""
        return self.raw.get(dp_name)

    def get_byte_at(self, dp_name: str, index: int) -> int | None:
        """Get a single byte from a multi-byte data point."""
        data = self.raw.get(dp_name)
        if data is None or index >= len(data):
            return None
        return data[index]

    def get_array(self, dp_name: str, element_size: int) -> list[int] | None:
        """Get an array data point as a list of numbers."""
        data = self.raw.get(dp_name)
        if data is None:
            return None
        return parse_array_data(data, element_size)

    def _hardness(self, dp_name: str) -> int | float | None:
        """Return a hardness value in the configured unit.

        The vendor app multiplies the raw value by 0.1 for every unit
        except mg/L (index 0).
        """
        val = self.get_number(dp_name)
        if val is None:
            return None
        if self.hardness_unit_index in (None, 0):
            return val
        return val / 10

    @property
    def incoming_hardness(self) -> int | float | None:
        return self._hardness("incoming_hardness")

    @property
    def outgoing_hardness(self) -> int | float | None:
        return self._hardness("outgoing_hardness")

    @property
    def hardness_unit_index(self) -> int | None:
        return self.get_number("hardness_unit")

    @property
    def valve_state(self) -> int | None:
        # Byte 0 of g_ucRegenStatus, per the vendor app
        return self.get_byte_at("regen_status", 0)

    @property
    def regen_countdown(self) -> int | None:
        # Byte 1 of g_ucRegenStatus: remaining time in the current
        # regeneration phase in seconds (app displays it as mm:ss)
        return self.get_byte_at("regen_status", 1)

    @property
    def flow_current(self) -> int | None:
        return self.get_number("flow_current")

    @property
    def remaining_capacity(self) -> int | None:
        return self.get_number("remaining_capacity_l")

    @property
    def remaining_capacity_pct(self) -> int | None:
        return self.get_number("remaining_capacity_pct")

    @property
    def total_capacity(self) -> int | None:
        return self.get_number("total_capacity")

    @property
    def regen_flow_setting(self) -> int | None:
        return None  # TODO: find in binary dump

    @property
    def total_hardness_removal(self) -> int | None:
        return self.get_number("total_caco3")

    @property
    def salt_level(self) -> int | None:
        return self.get_number("salt_level")

    @property
    def days_to_next_regen(self) -> int | None:
        # Try both data points (full dump vs periodic)
        val = self.get_number("est_days_to_next")
        if val is None:
            val = self.get_number("next_regen_days")
        return val

    @property
    def daily_water_usage_avg(self) -> int | None:
        return self.get_number("daily_water_usage_avg")

    @property
    def alarm_active(self) -> bool | None:
        # The vendor app raises the "Valve State Check" alarm when
        # byte 0 of g_ulERRLog0 equals 1
        err = self.get_byte_at("error_log", 0)
        if err is None:
            return None
        return err == 1

    @property
    def salt_refill_needed(self) -> bool | None:
        # g_ucCurrentSaltLevel is a status flag, not a level: the app
        # shows "Check Salt Level" when it is 0, "Normal operation"
        # otherwise
        val = self.get_number("salt_level")
        if val is None:
            return None
        return val == 0

    @property
    def regen_enabled(self) -> bool | None:
        val = self.get_number("regen_enabled")
        if val is None:
            return None
        return val != 0

    @property
    def is_regenerating(self) -> bool | None:
        vs = self.valve_state
        if vs is None:
            return None
        # Regen status byte 0: 0=in service, other=regenerating
        return (vs & 0xFF) != 0

    @property
    def error_log(self) -> int | None:
        return self.get_number("error_log")

    @property
    def today_vol(self) -> int | None:
        return self.get_number("today_vol")

    @property
    def total_vol(self) -> int | None:
        return self.get_number("total_vol")

    @property
    def peak_flow(self) -> int | None:
        return self.get_number("peak_flow")

    @property
    def regen_times_total(self) -> int | None:
        return self.get_number("regen_times_total")

    @property
    def daily_usage_2h(self) -> list[int] | None:
        return None

    @property
    def weekly_flow_avg(self) -> list[int] | None:
        return None

    @property
    def monthly_flow_avg(self) -> list[int] | None:
        return None

    @property
    def weekly_water_usage(self) -> list[int] | None:
        return None
