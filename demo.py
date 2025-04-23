from diot import DIOTCrateManager
from diot.utils.ftdi_utils import find_serial_numbers
import sys
import time
import pprint
import os
import pandas as pd

N_CARDS = 1
OT_SHUTDOWN = 80
HYSTERESIS = 75

CHPOWER = 3
HOTCH = [0]
INTERVAL = 5 # seconds
DURATION = 300 # seconds

RESULTS_DIR = os.path.join(os.getcwd(), "diot_test_results")
    
os.makedirs(RESULTS_DIR, exist_ok=True)


serial_numbers = sorted(find_serial_numbers(), key=lambda x: int(x[2:]))

# let's take only the first one
if not serial_numbers:
    print("No DIOT cards (with DTxx serial numbers) found.")
    sys.exit(1)

serial_numbers = serial_numbers[:N_CARDS]
print(serial_numbers)

crate_manager = DIOTCrateManager(
    serial_numbers=serial_numbers,
    ot_shutdown=OT_SHUTDOWN,
    hysteresis=HYSTERESIS,
)

card = crate_manager.get_card(serial_numbers[0])

hot_channel = [card.get_channel(ch) for ch in HOTCH]
for ch in hot_channel:
    ch.load_power = CHPOWER
    print(f"Set load power for card {serial_numbers[0]}, channel {ch} to {CHPOWER} W")


t0 = time.monotonic()
t = t0
prev_t = t
measurements = []
try:
    while time.monotonic() - t0 < DURATION:
        t = time.monotonic()
        if t - prev_t < INTERVAL:
            time.sleep(0.1)
        else:
            report = card.get_measurements()
            tmp = {
                "time": t - t0,
                "voltage": report["voltage"],
                "current": report["current"],
                "channels": [
                    {
                        "channel": i,
                        "load_power": report["channels"][i]["load_power"],
                        "temperature": report["channels"][i]["temperature"],
                    }
                    for i in range(16)
                ]
            }
            pprint.pp(tmp)
            measurements.append(tmp)
            temp_ch0 = report["channels"][0]["temperature"]
            if temp_ch0 + 2 > OT_SHUTDOWN:
                print(f"Over-temperature shutdown on channel {0} at {temp_ch0}°C")
                break

            prev_t = t
finally:
    # pass
    card.shutdown_all_loads() 


filename = os.path.join(RESULTS_DIR, f"measurements_{serial_numbers[0]}_{time.strftime('%Y%m%d_%H%M%S')}.csv")
df = pd.DataFrame(measurements)
print(df)
df.to_csv(filename, index=False)
# print(f"Measurements saved to {filename}")


print("Measurements:")
pprint.pp(measurements)
print("Done.")