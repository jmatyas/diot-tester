# SPDX-FileCopyrightText: 2023 Jakub Matyas for Warsaw University of Technology
#
# SPDX-License-Identifier: MIT

import digitalio

from sinara_mgmt.description_manager import SystemDescription
from sinara_mgmt.kasli import KasliI2C

kasli = KasliI2C(frequency=400000)
eui48 = kasli.eeprom.eui48
print("Kasli EUI-48: 0x", "-".join([f"{x:02x}" for x in eui48]))

contents = kasli.eeprom.contents
print("Contents", contents)

kasli.discover_peripherals()


SD = SystemDescription(kasli.sinara_eeprom, kasli.eem_peripherals)
SD.gen_system_description()
print(SD.description)
SD.dump_description("test_variant_normal")


led0 = kasli.expander0.get_pin(6)
led1 = kasli.expander0.get_pin(14)

led0.direction = digitalio.Direction.OUTPUT
led1.direction = digitalio.Direction.OUTPUT

led0.value = 1
led1.value = 1
