# make_cache.py
#!/usr/bin/env python3
import os
import json
import time
import argparse
from pymodbus.client import ModbusTcpClient

CACHE_FILE = "/tmp/growatt_cache.txt"
MODBUS_HOST = "192.168.10.105"
MODBUS_PORT = 4196
DEVICE_ID = 1


def to_watt(regs, i):
    return ((regs[i] << 16) + regs[i + 1]) * 0.1


def read_status(host: str = MODBUS_HOST, port: int = MODBUS_PORT) -> dict:
    client = ModbusTcpClient(host, port=port)
    try:
        if not client.connect():
            raise ConnectionError(f"Could not connect to Modbus server {host}:{port}")

        pv = client.read_input_registers(address=1, count=2, device_id=DEVICE_ID)
        if pv.isError():
            raise IOError(f"Ppv read error: {pv}")
        ppv_watt = to_watt(pv.registers, 0)  # 1,2 Ppv H,L

        r = client.read_input_registers(address=1000, count=43, device_id=DEVICE_ID)
        if r.isError():
            raise IOError(f"Storage block read error: {r}")
        regs = r.registers
        sys_mode = regs[0]                 # 1000
        soc = regs[14]                     # 1014
        charge_watt = to_watt(regs, 11)    # 1011,1012 Pcharge1 H,L
        export_watt = to_watt(regs, 29)    # 1029,1030 Pactogrid total H,L

        return {
            "timestamp": time.time(),
            "pactogrid": export_watt / 1000.0,  # kW, matches main.py's threshold units
            "ppv":       ppv_watt / 1000.0,     # kW
            "soc":       float(soc),
            "status":    sys_mode,
            "charging":  charge_watt > 0,
        }
    finally:
        client.close()


def make_cache(cache_file: str = CACHE_FILE, host: str = MODBUS_HOST, port: int = MODBUS_PORT):
    try:
        record = read_status(host, port)
    except Exception as e:
        print(f"❌ Modbus read failed ({e}), caching zeros")
        record = {
            "timestamp": time.time(),
            "pactogrid": 0.0,
            "ppv":       0.0,
            "soc":       0.0,
            "status":    0,
            "charging":  False,
        }

    # load existing cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except Exception:
            data = []
    else:
        data = []

    # append new record and keep last two entries
    data.append(record)
    data = data[-2:]

    # write back the cache
    with open(cache_file, "w") as f:
        json.dump(data, f)

    print(f"✅ Cache updated, stored {len(data)} records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default=CACHE_FILE,
                        help="Cache file path")
    parser.add_argument("--host", default=MODBUS_HOST,
                        help="Modbus TCP server host")
    parser.add_argument("--port", type=int, default=MODBUS_PORT,
                        help="Modbus TCP server port")
    args = parser.parse_args()
    make_cache(args.output, args.host, args.port)
