#!/usr/bin/env python3
import argparse
from pymodbus.client import ModbusTcpClient

MODBUS_HOST = "192.168.10.105"
MODBUS_PORT = 4196
DEVICE_ID = 1

PRIORITY_REGISTER = 1044
PRIORITY_MODES = {"load": 0, "battery": 1, "grid": 2}
PRIORITY_NAMES = {v: k for k, v in PRIORITY_MODES.items()}


def set_priority(mode: str, host: str = MODBUS_HOST, port: int = MODBUS_PORT, device_id: int = DEVICE_ID) -> int:
    client = ModbusTcpClient(host, port=port)
    try:
        if not client.connect():
            raise ConnectionError(f"Could not connect to Modbus server {host}:{port}")

        result = client.write_register(address=PRIORITY_REGISTER, value=PRIORITY_MODES[mode], device_id=device_id)
        if result.isError():
            raise IOError(f"Write error: {result}")

        readback = client.read_holding_registers(address=PRIORITY_REGISTER, count=1, device_id=device_id)
        if readback.isError():
            raise IOError(f"Readback error: {readback}")
        return readback.registers[0]
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Set Growatt inverter priority mode (holding register 1044)")
    parser.add_argument("mode", choices=sorted(PRIORITY_MODES), help="Priority mode to set")
    parser.add_argument("--host", default=MODBUS_HOST, help="Modbus TCP server host")
    parser.add_argument("--port", type=int, default=MODBUS_PORT, help="Modbus TCP server port")
    parser.add_argument("--device-id", type=int, default=DEVICE_ID, help="Modbus device/unit ID")
    args = parser.parse_args()

    current = set_priority(args.mode, args.host, args.port, args.device_id)
    print(f"Priority set to '{args.mode}' (register {PRIORITY_REGISTER} now reads {current}: {PRIORITY_NAMES.get(current, 'unknown')})")


if __name__ == "__main__":
    main()
