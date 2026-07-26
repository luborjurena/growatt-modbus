from pymodbus.client import ModbusTcpClient

MODBUS_HOST = "192.168.10.105"
MODBUS_PORT = 4196
DEVICE_ID = 1


def regs_to_ascii(regs):
    chars = []
    for v in regs:
        chars.append(chr((v >> 8) & 0xFF))
        chars.append(chr(v & 0xFF))
    return "".join(chars).strip("\x00 ")


client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
client.connect()

# Holding registers 9-14: Fw version H,M,L (main firmware) + Fw version2 H,M,L
# (control firmware), per the Growatt protocol PDF. ASCII, ordered high to low.
h = client.read_holding_registers(address=9, count=6, device_id=DEVICE_ID)
if not h.isError():
    hr = h.registers
    fw_version = regs_to_ascii(hr[0:3])
    fw_version2 = regs_to_ascii(hr[3:6])
    print(f"Firmware version: {fw_version}")
    print(f"Control firmware version: {fw_version2}")
else:
    print("Chyba (fw version):", h)

# Holding registers 82-88: FW Build No.5-0 (model letters + DSP1/DSP2/CPLD/M3
# build codes, ASCII) and Modbus Version (int, e.g. 207 means V2.07).
b = client.read_holding_registers(address=82, count=7, device_id=DEVICE_ID)
if not b.isError():
    br = b.registers
    model_version = regs_to_ascii(br[0:2])  # 82,83 FW Build No.5,4
    dsp1_build = regs_to_ascii([br[2]])     # 84 FW Build No.3
    dsp2_build = regs_to_ascii([br[3]])     # 85 FW Build No.2
    cpld_build = regs_to_ascii([br[4]])     # 86 FW Build No.1
    m3_build = regs_to_ascii([br[5]])       # 87 FW Build No.0
    modbus_version = br[6]                  # 88
    print(f"Model version: {model_version}")
    print(f"DSP1 FW build: {dsp1_build}")
    print(f"DSP2/M0 FW build: {dsp2_build}")
    print(f"CPLD/AFCI FW build: {cpld_build}")
    print(f"M3 FW build: {m3_build}")
    print(f"Modbus protocol version: V{modbus_version // 100}.{modbus_version % 100:02d} (raw {modbus_version})")
else:
    print("Chyba (FW build/Modbus version):", b)

# Input registers 1093-1104: BMS software version fields, per the Growatt
# protocol PDF. No format/unit is documented for these, so values are raw.
r1 = client.read_input_registers(address=1093, count=12, device_id=DEVICE_ID)
if not r1.isError():
    rr1 = r1.registers
    bms_fw = rr1[0]                  # 1093 BMS_FW
    bms_mcu_version = rr1[8]         # 1101 BMS_MCUVersion
    bms_gauge_version = rr1[9]       # 1102 BMS_GaugeVersion
    bms_gauge_fr_version = (rr1[11] << 16) | rr1[10]  # 1104 H16, 1103 L16 BMS_wGaugeFRVersion
    print(f"BMS_FW (1093, raw): {bms_fw}")
    print(f"BMS MCU software version (1101, raw): {bms_mcu_version}")
    print(f"BMS Gauge version (1102, raw): {bms_gauge_version}")
    print(f"BMS Gauge FR version (1103-1104, raw): {bms_gauge_fr_version}")
else:
    print("Chyba (BMS version 1093-1104):", r1)

# Input registers 1216-1217: BMS_HighestSoftVersion, BMS_HardwareVersion, per
# the Growatt protocol PDF. No format/unit documented, values are raw.
r2 = client.read_input_registers(address=1216, count=2, device_id=DEVICE_ID)
if not r2.isError():
    rr2 = r2.registers
    bms_highest_soft_version = rr2[0]  # 1216
    bms_hardware_version = rr2[1]      # 1217
    print(f"BMS highest software version (1216, raw): {bms_highest_soft_version}")
    print(f"BMS hardware version (1217, raw): {bms_hardware_version}")
else:
    print("Chyba (BMS version 1216-1217):", r2)

client.close()
