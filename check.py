from pymodbus.client import ModbusTcpClient


def to_watt(regs, i):
    return ((regs[i] << 16) + regs[i + 1]) * 0.1


def to_signed16(v):
    return v - 0x10000 if v >= 0x8000 else v


# Reason codes for register 1568 (DischargeToStandbyReason). Not present in the
# bundled Growatt protocol PDF; taken from field observation / vendor support.
DISCHARGE_TO_STANDBY_REASONS = {
    9: "Bat temp out of range",
    11: "Forbid by BMS",
}

client = ModbusTcpClient('192.168.10.105', port=4196)
client.connect()

pv = client.read_input_registers(address=1, count=2, device_id=1)
if not pv.isError():
    pv_watt = to_watt(pv.registers, 0)  # 1,2 Ppv H,L
    print(f"PV Power: {pv_watt:.1f} W")
else:
    print("Chyba (Ppv):", pv)

r = client.read_input_registers(address=1000, count=121, device_id=1)
if not r.isError():
    regs = r.registers
    sys_mode = regs[0]          # 1000
    soc = regs[14]              # 1014
    vbat = regs[13] / 10.0      # 1013
    batt_temp = regs[40] / 10.0 # 1040
    charge_watt = to_watt(regs, 11)       # 1011,1012 Pcharge1 H,L
    consumption_watt = to_watt(regs, 37)  # 1037,1038 PLocalLoad total H,L
    import_watt = to_watt(regs, 21)       # 1021,1022 PactouserTotal H,L
    export_watt = to_watt(regs, 29)       # 1029,1030 Pactogrid total H,L
    cycle_count = regs[95]      # 1095 BMS_CycleCnt
    soh = regs[96]              # 1096 BMS_SOH
    bms_warn = regs[99]         # 1099 BMS_WarnInfo
    bms_soc = regs[86]                       # 1086 BMS_SOC
    bms_vbat = regs[87] / 10.0               # 1087 BMS_BatteryVolt
    bms_current = to_signed16(regs[88]) / 10.0  # 1088 BMS_BatteryCurr (signed)
    bms_batt_temp = regs[89] / 10.0          # 1089 BMS_BatteryTemp
    bms_max_curr = regs[90]                  # 1090 BMS_MaxCurr (max charge/discharge current from BMS/pylon, scale unconfirmed)
    fault_words = regs[1:9]     # 1001-1008 Systemfault word0-7 (no bit-level reference in this doc)

    print(f"SysWorkMode: {sys_mode} (0x{sys_mode:02x})")
    print(f"SOC: {soc}%")
    print(f"Vbat: {vbat:.1f} V")
    print(f"Battery temp: {batt_temp:.1f} °C")
    print(f"Charging: {charge_watt:.1f} W")
    print(f"Consumption: {consumption_watt:.1f} W")
    print(f"Import: {import_watt:.1f} W")
    print(f"Export: {export_watt:.1f} W")
    print(f"Battery SOH: {soh}%")
    print(f"Battery cycles: {cycle_count}")
    print(f"BMS cross-check: SOC {bms_soc}% (inverter {soc}%), "
          f"Vbat {bms_vbat:.1f} V (inverter {vbat:.1f} V), "
          f"current {bms_current:.1f} A, temp {bms_batt_temp:.1f} °C (inverter {batt_temp:.1f} °C)")
    print(f"BMS warning: {bms_warn if bms_warn else 'none'}")
    active_words = {1000 + i: w for i, w in enumerate(fault_words, start=1) if w}
    print(f"System fault words (raw, undocumented bits): {active_words if active_words else 'none'}")
else:
    print("Chyba:", r)
    bms_max_curr = None

# 1560-1568 block: not in the bundled protocol PDF, addresses/meaning per field notes.
d = client.read_input_registers(address=1560, count=9, device_id=1)
if not d.isError():
    dregs = d.registers
    bms_max_curr_1563 = dregs[3]        # 1563 BMS_MaxCurr
    discharge_power_limit = dregs[5]    # 1565 Discharge power limit (assumed %)
    standby_reason_code = dregs[8]      # 1568 DischargeToStandbyReason
    standby_reason = DISCHARGE_TO_STANDBY_REASONS.get(standby_reason_code, f"unknown ({standby_reason_code})")

    print(f"BMS_MaxCurr (1563): {bms_max_curr_1563}" +
          (f" (inverter reports {bms_max_curr} at 1090)" if bms_max_curr is not None else ""))
    print(f"Discharge power limit (1565): {discharge_power_limit}%" +
          ("  ⚠️ BMS is actively limiting discharge to 0" if discharge_power_limit == 0 else ""))
    print(f"DischargeToStandbyReason (1568): {standby_reason_code} ({standby_reason})")
else:
    print("Chyba (1560-1568):", d)

client.close()