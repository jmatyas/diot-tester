from diot import DIOTCard
from diot.utils.ftdi_utils import find_serial_numbers
from utils.scope import test_scope, ip

serials = sorted(find_serial_numbers(), key=lambda x: int(x[2:]))
card = DIOTCard(serial=serials[0], ot_shutdown=90)
card.set_pwm_frequency(1, 24)

assymetric_load = card.load_channels[-1]
assymetric_load.load_power = 3.0

# for i in range(5):
#     load = card.load_channels[i]
#     print(f"Setting load channel {i} to 2.5 W")
#     load.load_power = 2.5


try:
    ident = test_scope(ip)
    # while True:
    #     voltage = card.voltage
    #     current = card.current
    #     print(f"Voltage: {voltage} V, Current: {current} A")
except KeyboardInterrupt:
    pass
finally:
    print("Shutting down all loads...")
    card.shutdown_all_loads()
    assymetric_load.load_power = 0.0
