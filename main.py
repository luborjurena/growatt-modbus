#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime
import requests

# Constants
STATUS_FILE = "/tmp/heater_status.json"

STATUS_HISTORY_FILE = "/tmp/heater_status_history.json"

def in_time_window(start_str: str, end_str: str) -> bool:
    now   = datetime.now().time()
    start = datetime.strptime(start_str, "%H:%M").time()
    end   = datetime.strptime(end_str,   "%H:%M").time()
    return start <= now <= end

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def should_start_heater(pactogrid, ppv, soc, soc_thresh, export_thresh, pv_thresh):
    return (
        soc       >= soc_thresh and
        pactogrid >= export_thresh and
        ppv       >= pv_thresh
    )

def get_cached_status(cache_file="/tmp/growatt_cache.txt"):
    try:
        with open(cache_file) as f:
            data = json.load(f)
    except Exception:
        data = []
    if not data:
        print("❌ Cache is empty or unreadable, using zeros")
        return {"pactogrid": 0.0, "ppv": 0.0, "soc": 0.0, "status": 0, "charging": False}
    return data[-1]

def persist_and_act(decision: bool, input_id: int = 1):
    status_str = "OK" if decision else "NOT OK"

    # Load history
    history = []
    if os.path.exists(STATUS_HISTORY_FILE):
        try:
            history = json.load(open(STATUS_HISTORY_FILE)).get("history", [])
        except Exception:
            history = []

    # Append and trim
    history.append(status_str)
    history = history[-2:]
    json.dump({"history": history}, open(STATUS_HISTORY_FILE, "w"))

    # Only act when the last two match
    if len(history) == 2 and history[0] == history[1]:
        if status_str == "OK":
            print("▶️ Both last checks OK → starting water heater")
            url = f"http://192.168.10.20/set.xml?type=s&id={input_id}"
        else:
            print("⏸ Both last checks NOT OK → stopping water heater")
            url = f"http://192.168.10.20/set.xml?type=r&id={input_id}"

        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                action = "started" if status_str == "OK" else "stopped"
                print(f"✅ Water heater {action} successfully")
            else:
                print(f"❌ Heater command failed: HTTP {resp.status_code}")
        except requests.RequestException as e:
            print(f"❌ Heater command error: {e}")
    else:
        print(f"🔍 History {history} → waiting for two in a row before acting")

def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("-s","--start", default="06:00",
                            help="Earliest run time (HH:MM)")
        parser.add_argument("-e","--end", default="20:00",
                            help="Latest run time (HH:MM)")
        parser.add_argument("--soc-threshold",   type=float, default=60.0)
        parser.add_argument("--export-threshold",type=float, default=0.0)
        parser.add_argument("--pv-threshold",    type=float, default=2.0)
        parser.add_argument("--input_id", type=int, default=1)
        args = parser.parse_args()

        if not in_time_window(args.start, args.end):
            print(f"Script only runs between {args.start} and {args.end}")
            return

        cached = get_cached_status()
        pactogrid   = cached.get("pactogrid", 0.0)
        ppv         = cached.get("ppv", 0.0)
        soc         = cached.get("soc", 0.0)
        is_charging = cached.get("charging", False)
        sys_mode    = cached.get("status", 0)

        print(f"SOC:           {soc:.1f}%, threshold: {args.soc_threshold:.1f}%")
        print(f"Grid export:   {pactogrid:.2f} kW, threshold: {args.export_threshold:.2f} kW")
        print(f"PV production: {ppv:.2f} kW, threshold: {args.pv_threshold:.2f} kW")
        print(f"Charging:      {is_charging} (SysWorkMode {sys_mode})")

        decision = should_start_heater(
            pactogrid, ppv, soc,
            args.soc_threshold,
            args.export_threshold,
            args.pv_threshold
        )

        # ← Here’s where we now handle heater control with history
        persist_and_act(decision, args.input_id)
    except Exception as e:
        print(f"❌ Error: {e}")
        requests.get(f"http://192.168.10.20/set.xml?type=r&id={args.input_id}", timeout=5)
        print("Error, disabling interface")

if __name__ == "__main__":
    main()