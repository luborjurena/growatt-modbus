#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pymodbus.client import ModbusTcpClient

MODBUS_HOST = "192.168.10.105"
MODBUS_PORT = 4196
DEVICE_ID = 1

ZABBIX_SERVER = "127.0.0.1"
ZABBIX_PORT = 10051
ZABBIX_HOST = "FVE"  # host name as configured in the Zabbix frontend


def to_watt(regs, i):
    return ((regs[i] << 16) + regs[i + 1]) * 0.1


def read_metrics(host: str, port: int) -> dict:
    client = ModbusTcpClient(host, port=port)
    try:
        if not client.connect():
            raise ConnectionError(f"Could not connect to Modbus server {host}:{port}")

        pv = client.read_input_registers(address=1, count=2, device_id=DEVICE_ID)
        if pv.isError():
            raise IOError(f"Ppv read error: {pv}")
        pv_watt = to_watt(pv.registers, 0)  # 1,2 Ppv H,L

        r = client.read_input_registers(address=1000, count=97, device_id=DEVICE_ID)
        if r.isError():
            raise IOError(f"Storage block read error: {r}")
        regs = r.registers

        return {
            "fve.pv.power":          round(pv_watt, 1),
            "fve.charge.power":      round(to_watt(regs, 11), 1),  # 1011,1012 Pcharge1 H,L
            "fve.discharge.power":   round(to_watt(regs, 9), 1),   # 1009,1010 Pdischarge1 H,L
            "fve.consumption.power": round(to_watt(regs, 37), 1),  # 1037,1038 PLocalLoad total H,L
            "fve.import.power":      round(to_watt(regs, 21), 1),  # 1021,1022 PactouserTotal H,L
            "fve.export.power":      round(to_watt(regs, 29), 1),  # 1029,1030 Pactogrid total H,L
            "fve.battery.soc":       regs[14],                     # 1014
            "fve.battery.voltage":   round(regs[13] / 10.0, 1),    # 1013
            "fve.battery.temp":      round(regs[40] / 10.0, 1),    # 1040
            "fve.battery.soh":       regs[96],                     # 1096 BMS_SOH
            "fve.battery.cycles":    regs[95],                     # 1095 BMS_CycleCnt
        }
    finally:
        client.close()


def send_to_zabbix(metrics: dict, zabbix_server: str, zabbix_port: int, zabbix_host: str) -> bool:
    payload = "\n".join(f'"{zabbix_host}" {key} {value}' for key, value in metrics.items()) + "\n"
    try:
        result = subprocess.run(
            ["zabbix_sender", "-v", "-z", zabbix_server, "-p", str(zabbix_port),
             "-s", zabbix_host, "-i", "-"],
            input=payload, capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        print("❌ zabbix_sender binary not found (install the 'zabbix-sender' package)", file=sys.stderr)
        return False

    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modbus-host", default=MODBUS_HOST)
    parser.add_argument("--modbus-port", type=int, default=MODBUS_PORT)
    parser.add_argument("--zabbix-server", default=ZABBIX_SERVER)
    parser.add_argument("--zabbix-port", type=int, default=ZABBIX_PORT)
    parser.add_argument("--zabbix-host", default=ZABBIX_HOST,
                         help="Host name as configured in the Zabbix frontend")
    args = parser.parse_args()

    try:
        metrics = read_metrics(args.modbus_host, args.modbus_port)
    except Exception as e:
        print(f"❌ Modbus read failed: {e}", file=sys.stderr)
        sys.exit(1)

    ok = send_to_zabbix(metrics, args.zabbix_server, args.zabbix_port, args.zabbix_host)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
