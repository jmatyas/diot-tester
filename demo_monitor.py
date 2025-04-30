from diot import DIOTCrateManager, MonitoringSession
from diot.utils.ftdi_utils import find_serial_numbers
import sys

START_CARD = 0
N_CARDS = 8
OT_SHUTDOWN = 85
HYSTERESIS = 80

CARD_POWER = 30.0
INTERVAL = 1  # seconds
MINUTES = 30
DURATION = MINUTES * 60  # seconds

RESULTS_DIR = "tests"

serial_numbers = sorted(find_serial_numbers(), key=lambda x: int(x[2:]))

if not serial_numbers:
    print("No DIOT cards (with DTxx serial numbers) found.")
    sys.exit(1)

# serial_numbers = serial_numbers[:N_CARDS]
print(serial_numbers)

crate_manager = DIOTCrateManager(
    serial_numbers=serial_numbers[START_CARD : START_CARD + N_CARDS],
    ot_shutdown=OT_SHUTDOWN,
    hysteresis=HYSTERESIS,
)

# pprint.pprint(crate_manager.report_cards(shutdown_card_on_ot=False))

monitor_session = MonitoringSession(
    crate_manager, save_dir=RESULTS_DIR, session_name="test"
)

crate_manager.set_cards_load_power(serial_numbers[START_CARD], CARD_POWER)
try:
    monitor_session.monitor(
        duration=DURATION,
        interval=INTERVAL,
        shutdown_at_end=True,
        stop_on_ot=True,
        save_every_iteration=True,
        serials_to_monitor=serial_numbers[START_CARD : START_CARD + N_CARDS],
    )
finally:
    crate_manager.shutdown_all_loads()
