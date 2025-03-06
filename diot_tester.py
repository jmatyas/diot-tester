import os

from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.i2c import I2C as _I2C
from adafruit_bus_device import i2c_device
from busio import I2C

from chips.eeprom_24aa025e48 import EEPROM24AA025E48, EEPROM24AA02E48
from chips.lm75 import LM75
from chips.pca9544 import PCA9544
from chips.tca9548a import PCA9546A
from adafruit_pca9685 import PCA9685
from chips.mcp3221 import MCP3221



# patching ftdi_mpsse.mpsse.i2c.I2C.scan method so it accepts one argument
def patched_scan_method(self, write=False):
    return [addr for addr in range(0x79) if self._i2c.poll(addr, write)]


_I2C.scan = patched_scan_method


class DIOTTester(I2C):
    scan_blacklist = [0x70]

    def __init__(self, url="ftdi://ftdi:232:/1", frequency=100000):
        os.environ["BLINKA_FT232H"] = url
        self._i2c = _I2C(1, frequency=frequency)

        # 2 EEPROM to EEM0
        self.eeproms = [
            EEPROM24AA02E48(self._i2c, address=0x50),
            EEPROM24AA025E48(self._i2c, address=0x50),  # FIXME: collision
        ]

        # on i2c_mux.channels[0]:
        #   -> LM75_[8:15]
        # on i2c_mux.channels[1]:
        #   -> LM75_[0:7]
        # on i2c_mux.channels[2]:
        #   -> PWM_HEATERS[0:16] 
        #   -> MCP3221 current measurement
        # on i2c_mux.channels[3]:
        #   -> LM75_PSU[0:2]
        #   -> MCP3221 voltage measurement
        self.i2c_mux = PCA9546A(self._i2c, address=0x70) # FIXME
        self.i2c_buses = [
            self.i2c_mux[0],
            self.i2c_mux[1],
            self.i2c_mux[2],
            self.i2c_mux[3],
        ]

        # Mux channels 0 and 1 swapped
        self.lm75s = [
            LM75(self.i2c_buses[1], address=0x48 + addr) for addr in range(8)
        ] + [
            LM75(self.i2c_buses[0], address=0x48 + addr) for addr in range(8)
        ]

        self.i_monitor = MCP3221(self.i2c_buses[2], address=0x4D, reference_voltage=3.3)
        self.v_monitor = MCP3221(self.i2c_buses[3], address=0x4D, reference_voltage=3.3)
        self.pwm_chip = PCA9685(self.i2c_buses[2])

        self.pwm_channels = [
            self.pwm_chip.channels[i] for i in range(16)
        ]

        self.psu_lm75s = [
            LM75(self.i2c_buses[3], address=0x48 + addr) for addr in range(3)
        ]

        




