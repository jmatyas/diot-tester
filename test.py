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
    logging.basicConfig(level=logging.DEBUG)
    # tester = Test()

    # print(tester.ee.test_contents(4))
    # logger.debug("done")
    # # def print_reg(reg):
    # #     print(f"0b{reg:08b} 0x{reg:02x}")

    from pyftdi.ftdi import Ftdi
    from pyftdi.eeprom import FtdiEeprom
    from pyftdi.misc import hexdump
    import sys
    import struct

    # EEPROM chip type (0x46, 0x56 or 0x66)
    CHIP_TYPE = 0x46

    eeprom = FtdiEeprom()
    eeprom.open('ftdi://ftdi:ft232h/1', model="93C46")
    print(eeprom._size) # in 8 bit bytes -> 128 * 8 =1024 bits = 1Kbit
    eeprom._chip = CHIP_TYPE
    # print(eeprom._chip)
    # print(eeprom.default_size)
    # print(eeprom.size)

    # NOTE: pyftd.misc.hexdump operates on 16 bit words, not on 8 bit bytes,
    # which generates 2 times lareger output; it had to be patched   
    print('Dumping current EEPROM config')
    # eeprom.dump_config()
    print(hexdump(eeprom.data, full=True))

    try:
        if eeprom.has_serial:
            print('FTDI has SN already assigned, aborting!')
            # sys.exit(1)
    except AttributeError:
        pass

    eeprom.initialize()
    # funny thing - if strings are more than 29 characters long, pyftdi throws an error
    # that it can't fit strings into EEPROM, and the message says that it's 2 oversize
    # characters... but when it's set to 29 characters, it works fine... (according to pyFTDI,
    # but in reality, it produces non standard characters)... so it should be 28 characters
    eeprom.set_manufacturer_name('WUT ISE')
    eeprom.set_product_name('DIOT Tester v1')
    eeprom.set_serial_number('DT01')
    chipoff = eeprom._PROPERTIES[eeprom.device_version].chipoff
    useroff = eeprom._PROPERTIES[eeprom.device_version].user

    # https://www.ftdichip.com/Documents/AppNotes/AN_121_FTDI_Device_EEPROM_User_Area_Usage.pdf
    # When connected to 93C46 EEPROM (128 bytes) there is one block of memory space
    # available as user area. Size depends on the length of the Manufacturer, ManufacturerId,
    # Description and SerialNumber strings. Max length of Manufacturer, ManufacturerId,
    # Description and SerialNumber strings is 48 (16 bits) words. If all the 48 words are used
    # there is no user area space left.
    # 
    # User area space (in bytes) = (48 - (Manufacturer + Description + ManufacturerId + SerialNumber)) * 2
    # Start adress = the address following the last byte of SerialNumber string

    print(f"Chip type: 0x{eeprom._chip:02x}")
    print(f"EEPROM size: 0x{eeprom.default_size:02x}")
    print(f"Device version: 0x{eeprom.device_version:02x}")
    print(f"Chip offset: 0x{chipoff:02x}")
    print(f"User offset: 0x{useroff:02x}")
    print(f"size: {eeprom._size} bytes")

    # size=256, user=0x1A, dynoff = 0xA0, chipoff=0x1E

    eeprom._eeprom[chipoff] = CHIP_TYPE

    # Bit 4 - CH A driver - if 1 VCP else D2xx
    # Bits [3:0] - channel type
    eeprom._eeprom[0x00] = 0x00
    
    # Bit 4 - Power save disable
    # Bit 3 - FT1284 flow control
    # Bit 2 - FT1283 DATA LSB
    # Bit 1 - FT1284 clock IDLE state
    eeprom._eeprom[0x01] = 0x10

    # 0x02:0x03 - Vendor id
    # 0x04:0x05 - Product id
    # 0x06:0x07 - Device release number

    # - Bit 7 - always 1
    # - Bit 6: 1 if self powered, 0 if bus powered
    # - Bit 5: 1 if uses remote wakeup, 0 if not
    eeprom._eeprom[0x08] = 0xC0
    eeprom._eeprom[0x09] = 0x96 # 150 mA


    # Addr 0A: Chip configuration
    # Bit 7: 0 - reserved
    # Bit 6: 0 - reserved
    # Bit 5: 0 - reserved
    # Bit 4: 1 - Change USB version on BM and 2232C
    # Bit 3: 1 - Use the serial number string
    # Bit 2: 1 - Enable suspend pull downs for lower power
    # Bit 1: 1 - Out EndPoint is Isochronous
    # Bit 0: 1 - In EndPoint is Isochronous
    eeprom._eeprom[0x0a] = 0x08


    # # - group settings, other FT4232H dongles have 0 here
    # eeprom._eeprom[0x0c] = 0x00 # ?
    # eeprom._eeprom[0x0d] = 0x00 # ?

    # 0x18 - 0x1D - CBUS functions

    # # Manufacturing string
    man_string_off , man_string_length = eeprom._eeprom[0x0E]-0x80, eeprom._eeprom[0x0F]
    print(man_string_off, man_string_length) # 0xC0 - 0x80 = 0x40, 0x0A - man_string_off, man_string_length 
    # # Product string
    prod_string_off, prod_string_length = eeprom._eeprom[0x10]-0x80, eeprom._eeprom[0x11] 
    print(prod_string_off, prod_string_length)
    # # Serial number string
    serial_string_off, serial_string_length = eeprom._eeprom[0x12]-0x80, eeprom._eeprom[0x13]
    print(serial_string_off, serial_string_length)


    bstream = bytearray()
    bstream.extend("DT_SLOT_01\0".encode("utf-8"))
    eeprom._eeprom[useroff:useroff+len(bstream)] = bstream


    print(hexdump(eeprom.data, full=True))



    eeprom._dirty.add('eeprom')
    eeprom.sync()
    # eeprom.dump_config()


    # eeprom.commit(dry_run=False)


    eeprom.close()

    print(Ftdi.list_devices())



    