# Growatt FVE Modbus Automation

Local Modbus TCP monitoring and automation for a Growatt hybrid inverter (SPH-type storage system) — no dependency on Growatt's cloud API. Covers three things:

- reading live inverter/battery state directly over Modbus TCP
- automatically switching a water heater on/off based on solar surplus
- pushing metrics to Zabbix via `zabbix_sender`

## Components

- **`check.py`** — one-shot diagnostic dump: PV power, battery state (SOC, voltage, temp, SOH, cycle count), charge/discharge/consumption/export power, and a BMS-vs-inverter cross-check. Useful for manually verifying the Modbus link and register mapping.
- **`check_version.py`** — one-shot dump of inverter firmware/build versions and BMS software/hardware version registers. The BMS version fields (input registers 1093, 1101, 1102, 1216, 1217) have no documented format/unit and may read as `0` if the connected BMS/battery pack doesn't populate them.
- **`make_cache.py`** — polls the Modbus server and writes a small rolling cache (`/tmp/growatt_cache.txt`) of PV power, grid export, SOC, and charging state. Decouples data collection from the heater-control decision below; on a Modbus failure it caches zeros instead of crashing.
- **`main.py`** — reads that cache and decides whether to turn the water heater on/off via an HTTP relay, based on SOC/export/PV thresholds. Requires two consecutive matching decisions before acting (debounce), and always fails safe to "off" on error.
- **`send_zabbix.py`** — reads live values directly from Modbus (PV power, charge/discharge/consumption/import/export power, SOC, voltage, temp, SOH, cycle count) and pushes them to a Zabbix server in one batch via `zabbix_sender`.
- **`systemd/`** — service + timer units to run `make_cache.py` → `main.py` (chained via `OnSuccess=`) every 5 minutes during daylight hours, and `send_zabbix.py` every 5 minutes around the clock.
- **`zabbix/template_fve_inverter.yaml`** — importable Zabbix template: trapper items matching `send_zabbix.py`'s keys, a no-data trigger, and graphs (power flow, battery power, battery charge state, battery voltage/temperature).

## Register map

Register addresses and scaling factors come from Growatt's official "Inverter Modbus RTU Protocol_II" document, which is **not included in this repo** — it carries a "no reproduction without permission" copyright notice. Request it from Growatt or your inverter's distributor. The two register blocks used here:

- Base group (address `0`-`124`): PV production power
- Storage group (address `1000`-`1124`): battery, grid, load, and BMS registers

## Setup

1. Create a venv and install dependencies:
   ```sh
   python3 -m venv .
   ./bin/pip install -r requirements.txt
   ```
2. Adjust the Modbus host/port constants at the top of each script (default: `192.168.10.105:4196`) to match your Modbus TCP gateway, and the `device_id`/unit ID if different.
3. Adjust the heater relay URL in `main.py` (`http://192.168.10.20/set.xml`) to match your relay's control API.
4. Import `zabbix/template_fve_inverter.yaml` into Zabbix and link it to a host whose name matches `send_zabbix.py`'s `--zabbix-host` (default `FVE`).
5. Copy the `systemd/` unit files to `/etc/systemd/system/` (adjust `WorkingDirectory`/`ExecStart` if your deployment path isn't `/root/fve/`), then:
   ```sh
   systemctl daemon-reload
   systemctl enable --now fve-cache.timer
   systemctl enable --now fve-zabbix.timer
   ```

## License

MIT — see [LICENSE](LICENSE).
