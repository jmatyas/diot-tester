from diot import DIOTCrateManager, MonitoringSession
from diot.utils.ftdi_utils import find_serial_numbers
import sys
import time
import pprint
import os
import pandas as pd

START_CARD = 2
N_CARDS = 1
OT_SHUTDOWN = 85
HYSTERESIS = 80

CARD_POWER = 10
INTERVAL = 5 # seconds
MINUTES = 13
DURATION = MINUTES * 60 # seconds

RESULTS_DIR = "diot_test_results"
    
serial_numbers = sorted(find_serial_numbers(), key=lambda x: int(x[2:]))

# let's take only the first one
if not serial_numbers:
    print("No DIOT cards (with DTxx serial numbers) found.")
    sys.exit(1)

# serial_numbers = serial_numbers[:N_CARDS]
print(serial_numbers)

# chce móc ustawić moc na wszystkich kartach, a monitorować tylko na konkretnych

tmp_crate_manager = DIOTCrateManager(
    serial_numbers=serial_numbers,
    ot_shutdown=OT_SHUTDOWN,
    hysteresis=HYSTERESIS,
)

for serial in serial_numbers:
    tmp_crate_manager.set_card_load_power(serial, CARD_POWER)
del tmp_crate_manager

crate_manager = DIOTCrateManager(
    serial_numbers=serial_numbers[START_CARD:START_CARD + N_CARDS],
    ot_shutdown=OT_SHUTDOWN,
    hysteresis=HYSTERESIS,
)

# pprint.pprint(crate_manager.report_cards(shutdown_card_on_ot=False))

monitor_session = MonitoringSession(crate_manager, save_dir=RESULTS_DIR, session_name="test_monitoring")

# crate_manager.set_card_load_power(serial_numbers, CARD_POWER)
try:
    monitor_session.monitor(
        duration=DURATION,
        interval=INTERVAL,
        shutdown_at_end=True,
        stop_on_ot=True,
        save_every_iteration=True,
    )
finally:
    crate_manager.shutdown_all_loads()

