import os
import time

from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.i2c import I2C as _I2C
from adafruit_bus_device import i2c_device
from busio import I2C

from chips.eeprom_24aa025e48 import EEPROM24AA025E48, EEPROM24AA02E48
from chips.lm75 import LM75
from chips.pca9544 import PCA9544A
from adafruit_pca9685 import PCA9685
from chips.mcp3221 import MCP3221
import logging

logger = logging.getLogger(__name__)


# patching ftdi_mpsse.mpsse.i2c.I2C.scan method so it accepts one argument
def patched_scan_method(self, write=False):
    return [addr for addr in range(0x78) if self._i2c.poll(addr, write)]


_I2C.scan = patched_scan_method


def make_i2c_graph(detected):
    first = 0x03
    last = 0x77
    header = "    " + " ".join([f"{x:2x}" for x in range(0x00, 0x10)])
    buffer = header

    for line_ix in range(0, 0x80, 0x10):
        line_contents = []
        for addr in range(line_ix, line_ix + 0x10):   
            if addr < first or addr > last:
                line_contents.append("  ")
            elif addr in detected:
                line_contents.append(f"{addr:02x}")
            else:
                line_contents.append("--")
        line = " ".join(line_contents)
        buffer += f"\n{line_ix:02x}: {line}"

    return buffer


class PCA:
    def __init__(self, i2c: I2C, address: int = 0x40) -> None:
        self._device = i2c_device.I2CDevice(i2c, address, probe=False)

    def _read_u8(self, address: int) -> int:
        with self._device as i2c:
            write_buffer = bytearray([address & 0xFF])
            read_buffer = bytearray(1)
            i2c.write_then_readinto(write_buffer, read_buffer)
        return read_buffer[0]

    def _write_u8(self, address: int, value: int) -> None:
        write_buffer = bytearray([address & 0xFF, value & 0xFF])
        with self._device as i2c:
            i2c.write(write_buffer)



class Test(I2C):
    scan_blacklist = [0x70]

    def __init__(self, url="ftdi://ftdi:232h:/1", frequency=50000):
        os.environ["BLINKA_FT232H"] = url
        self._i2c = _I2C(frequency=frequency)

        self.ee = EEPROM24AA02E48(self, address=0x50)





if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)
    # tester = Test()

    # print(tester.ee.test_contents(4))
    # logger.debug("done")
    # # def print_reg(reg):
    # #     print(f"0b{reg:08b} 0x{reg:02x}")


    from pyftdi.i2c import I2cController
    from pyftdi.i2c import I2cNackError

    i2c = I2cController()
    i2c.configure("ftdi://ftdi:232h/1", frequency=50000)
    port = i2c.get_port(0x50)
    data = port.exchange([0x0], 1)
