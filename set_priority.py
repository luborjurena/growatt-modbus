#!/usr/bin/env python3
import argparse
from pymodbus.client import ModbusTcpClient

MODBUS_HOST = "192.168.10.105"
MODBUS_PORT = 4196
DEVICE_ID = 1

PRIORITY_REGISTER = 1044
PRIORITY_MODES = {"load": 0, "battery": 1, "grid": 2}
PRIORITY_NAMES = {v: k for k, v in PRIORITY_MODES.items()}

# BatFirstPowerRate: charge power rate (% of rated power) applied when
# Priority is set to Battery. Has no effect in other modes.
BAT_CHARGE_POWER_RATE_REGISTER = 1090

# AC charge switch when Priority is Battery (1=allow charging from AC, 0=forbid).
AC_CHARGE_REGISTER = 1092
AC_CHARGE_MODES = {"forbid": 0, "allow": 1}
AC_CHARGE_NAMES = {v: k for k, v in AC_CHARGE_MODES.items()}

# Schedule slot 1 per priority mode: start/stop time (hour packed in the high
# byte, minute in the low byte) plus the switch that enables the slot.
BAT_FIRST_START_TIME_REGISTER = 1100
BAT_FIRST_STOP_TIME_REGISTER = 1101
BAT_FIRST_SLOT1_ENABLE_REGISTER = 1102

GRID_FIRST_START_TIME_REGISTER = 1080
GRID_FIRST_STOP_TIME_REGISTER = 1081
GRID_FIRST_SLOT1_ENABLE_REGISTER = 1082

SCHEDULE_REGISTERS = {
    "battery": (BAT_FIRST_START_TIME_REGISTER, BAT_FIRST_STOP_TIME_REGISTER, BAT_FIRST_SLOT1_ENABLE_REGISTER),
    "grid": (GRID_FIRST_START_TIME_REGISTER, GRID_FIRST_STOP_TIME_REGISTER, GRID_FIRST_SLOT1_ENABLE_REGISTER),
}
SCHEDULE_LABELS = {"battery": "Bat First", "grid": "Grid First"}


def parse_time(value: str) -> int:
    try:
        hour_str, minute_str = value.split(":")
        hour, minute = int(hour_str), int(minute_str)
    except ValueError:
        raise ValueError(f"invalid time '{value}', expected HH:MM") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid time '{value}', expected HH:MM within 00:00-23:59")
    return (hour << 8) | minute


def format_time(value: int) -> str:
    return f"{value >> 8:02d}:{value & 0xFF:02d}"


def set_priority(mode: str, power_rate: int = None, start_time: str = None, end_time: str = None,
                  ac_charge: str = None, host: str = MODBUS_HOST, port: int = MODBUS_PORT,
                  device_id: int = DEVICE_ID) -> dict:
    client = ModbusTcpClient(host, port=port)
    try:
        if not client.connect():
            raise ConnectionError(f"Could not connect to Modbus server {host}:{port}")

        def write(address, value, label):
            result = client.write_register(address=address, value=value, device_id=device_id)
            if result.isError():
                raise IOError(f"Write error ({label}): {result}")

        def read(address, label):
            result = client.read_holding_registers(address=address, count=1, device_id=device_id)
            if result.isError():
                raise IOError(f"Readback error ({label}): {result}")
            return result.registers[0]

        write(PRIORITY_REGISTER, PRIORITY_MODES[mode], "priority")

        if power_rate is not None:
            write(BAT_CHARGE_POWER_RATE_REGISTER, power_rate, "power rate")

        if start_time is not None and end_time is not None:
            start_reg, stop_reg, enable_reg = SCHEDULE_REGISTERS[mode]
            write(start_reg, parse_time(start_time), "start time")
            write(stop_reg, parse_time(end_time), "end time")
            write(enable_reg, 1, "schedule enable")

        if ac_charge is not None:
            write(AC_CHARGE_REGISTER, AC_CHARGE_MODES[ac_charge], "AC charge")

        readback = {"priority": read(PRIORITY_REGISTER, "priority")}
        if power_rate is not None:
            readback["power_rate"] = read(BAT_CHARGE_POWER_RATE_REGISTER, "power rate")
        if start_time is not None and end_time is not None:
            start_reg, stop_reg, enable_reg = SCHEDULE_REGISTERS[mode]
            readback["start_time"] = read(start_reg, "start time")
            readback["end_time"] = read(stop_reg, "end time")
        if ac_charge is not None:
            readback["ac_charge"] = read(AC_CHARGE_REGISTER, "AC charge")

        return readback
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Set Growatt inverter priority mode (holding register 1044)")
    parser.add_argument("mode", choices=sorted(PRIORITY_MODES), help="Priority mode to set")
    parser.add_argument("--power-rate", type=int, metavar="0-100",
                         help="Charge power rate to set when mode is 'battery' (percent of rated power, "
                              "register 1090)")
    parser.add_argument("--start-time", metavar="HH:MM",
                         help="Schedule start time when mode is 'battery' or 'grid' "
                              "(register 1100/1080 respectively, default 00:00)")
    parser.add_argument("--end-time", metavar="HH:MM",
                         help="Schedule end time when mode is 'battery' or 'grid' "
                              "(register 1101/1081 respectively, default 23:59)")
    parser.add_argument("--ac-charge", choices=sorted(AC_CHARGE_MODES),
                         help="Allow/forbid charging from AC when mode is 'battery' (register 1092, default allow)")
    parser.add_argument("--host", default=MODBUS_HOST, help="Modbus TCP server host")
    parser.add_argument("--port", type=int, default=MODBUS_PORT, help="Modbus TCP server port")
    parser.add_argument("--device-id", type=int, default=DEVICE_ID, help="Modbus device/unit ID")
    args = parser.parse_args()

    if (args.power_rate is not None or args.ac_charge is not None) and args.mode != "battery":
        parser.error("--power-rate/--ac-charge only apply when mode is 'battery'")
    if (args.start_time is not None or args.end_time is not None) and args.mode not in SCHEDULE_REGISTERS:
        parser.error("--start-time/--end-time only apply when mode is 'battery' or 'grid'")

    if args.power_rate is not None and not 0 <= args.power_rate <= 100:
        parser.error("--power-rate must be between 0 and 100")

    start_time = end_time = ac_charge = None
    if args.mode in SCHEDULE_REGISTERS:
        start_time = args.start_time or "00:00"
        end_time = args.end_time or "23:59"
        try:
            parse_time(start_time)
            parse_time(end_time)
        except ValueError as e:
            parser.error(str(e))
    if args.mode == "battery":
        ac_charge = args.ac_charge or "allow"

    result = set_priority(args.mode, args.power_rate, start_time, end_time, ac_charge,
                           args.host, args.port, args.device_id)

    print(f"Priority set to '{args.mode}' (register {PRIORITY_REGISTER} now reads {result['priority']}: "
          f"{PRIORITY_NAMES.get(result['priority'], 'unknown')})")
    if "power_rate" in result:
        print(f"Charge power rate set (register {BAT_CHARGE_POWER_RATE_REGISTER} now reads {result['power_rate']}%)")
    if "start_time" in result:
        start_reg, stop_reg, _ = SCHEDULE_REGISTERS[args.mode]
        print(f"{SCHEDULE_LABELS[args.mode]} schedule set (register {start_reg} now reads "
              f"{format_time(result['start_time'])}, register {stop_reg} now reads "
              f"{format_time(result['end_time'])}, slot 1 enabled)")
    if "ac_charge" in result:
        print(f"AC charge set (register {AC_CHARGE_REGISTER} now reads {result['ac_charge']}: "
              f"{AC_CHARGE_NAMES.get(result['ac_charge'], 'unknown')})")


if __name__ == "__main__":
    main()
