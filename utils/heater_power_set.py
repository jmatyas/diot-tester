from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diot.cards import DIOTCard

p=1
heater_serial="DT00"

card = DIOTCard(serial=heater_serial)
aux = card.get_channel(16)
aux.load_power = p
temp_ch = card.get_channel(10)

input(f"Heating with power {p} W active, press Enter to switch off the heater"
                )
aux.load_power = 0
print("Temp after P=0 setting :", temp_ch.temperature_sensor.temperature)