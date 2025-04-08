import sys

from pyftdi.eeprom import FtdiEeprom
from pyftdi.ftdi import Ftdi
from pyftdi.misc import hexdump

MODEL = "93C46"
CHIP_TYPE = 0x46


MANUFACTURER = "WUT ISE"
PRODUCT = "DIOT Tester v1"
SERIAL = "DT00"

default_config = {
    # Bit 4 - CH A driver - if 1 VCP else D2xx
    # Bits [3:0] - channel type:
    #  - TYPE_AM=0,
    #  - TYPE_BM=1,
    #  - TYPE_2232C=2,
    #  - TYPE_R=3,
    #  - TYPE_2232H=4,
    #  - TYPE_4232H=5,
    #  - TYPE_232H=6,
    #  - TYPE_230X=7,
    0x00: 0x00,
    # Bit 4 - Power save disable
    # Bit 3 - FT1284 flow control
    # Bit 2 - FT1283 DATA LSB
    # Bit 1 - FT1284 clock IDLE state
    0x01: 0x10,
    # Addr 02:03 - Vendor id
    # Addr 04:05 - Product id
    # Addr 06:07 - Device release number
    # Addr 08: Config descriptor
    # - Bit 7 - always 1
    # - Bit 6: 1 if self powered, 0 if bus powered
    # - Bit 5: 1 if uses remote wakeup, 0 if not
    0x08: 0xC0,
    # Max current draw divided by 2
    0x09: 0x96,  # 150 mA
    # Addr 0A: Chip configuration
    # Bit 7: 0 - reserved
    # Bit 6: 0 - reserved
    # Bit 5: 0 - reserved
    # Bit 4: 1 - Change USB version on BM and 2232C
    # Bit 3: 1 - Use the serial number string
    # Bit 2: 1 - Enable suspend pull downs for lower power
    # Bit 1: 1 - Out EndPoint is Isochronous
    # Bit 0: 1 - In EndPoint is Isochronous
    0x0A: 0x08,
    # Addr 0B: Unused on FT232H
    # Addr 0C:0D - Group settings
    # 0x0c: 0x00 # ?
    # 0x0d: 0x00 # ?
    # Addr 0x18:0x1D - CBUS functions - we can leave it as default and program
    #   them in runtime
    #  Other settings are not well decoded and are not needed for now
}


def _default_config(ee, chip_type):
    chipoff = ee._PROPERTIES[ee.device_version].chipoff
    ee._eeprom[chipoff] = chip_type
    for addr, value in default_config.items():
        ee._eeprom[addr] = value


def configure_ftdi(
    url,
    manufacturer=MANUFACTURER,
    product=PRODUCT,
    serial=SERIAL,
    force=True,
    dry_run=True,
):
    ft_ee = FtdiEeprom()
    ft_ee.open(url, model=MODEL)
    ft_ee._chip = CHIP_TYPE
    try:
        if ft_ee.has_serial:
            print(f"FTDI has SN already assigned: ", ft_ee.serial)
            if force:
                print("Force writing new configuration...")
            else:
                print("Aborting...")
                return
    except AttributeError:
        pass

    ft_ee.initialize()
    # funny thing - if strings are more than 29 characters long, pyftdi throws an error
    # that it can't fit strings into EEPROM, and the message says that it's 2 oversize
    # characters... but when it's set to 29 characters, it works fine... (according to pyFTDI,
    # but in reality, it produces non-standard characters)... so it should be max 28 characters
    # of manufacturer + product name + serial number
    # So if Manufacturer + Product are standard, then the serial number can be max 7
    # characters
    man_len = len(manufacturer)
    prod_len = len(product)
    s_len = len(serial)
    if man_len + prod_len + s_len > 28:
        raise ValueError(
            "Manufacturer + Product + Serial number length exceeds 28 characters"
        )

    chipoff = ft_ee._PROPERTIES[ft_ee.device_version].chipoff
    useroff = ft_ee._PROPERTIES[ft_ee.device_version].user

    # According to FTDI user guide, the serial number should not start with digit
    # due to the fact that "systems will only recognize the first instance of such
    # a device"
    # See: https://ftdichip.com/wp-content/uploads/2020/07/AN_124_User_Guide_For_FT_PROG.pdf
    # Page 14, section 5.4 "USB Serial Number"
    # TODO: check if this is true for FT232H
    if serial[0].isdigit():
        raise ValueError("Serial number should not start with digit.")

    ft_ee.set_manufacturer_name(manufacturer)
    ft_ee.set_product_name(product)
    ft_ee.set_serial_number(serial)

    _default_config(ft_ee, ft_ee._chip)

    # FIXME: let's assume that the serial number is in format DTxx, where xx is
    # a number from 0 to 99 (more likely 0 to 9 for DIOT Tester crate) and denotes
    # the slot number the device is in.
    bstream = bytearray()
    bstream.extend(f"DT_SLOT_{serial[-2:]}\0".encode("utf-8"))
    ft_ee._eeprom[useroff : useroff + len(bstream)] = bstream

    ft_ee._dirty.add("eeprom")
    ft_ee.commit(dry_run=dry_run)
    ft_ee.sync()
    ft_ee.close()


def dump_ee_contents(url="ftdi://ftdi:232h:/1", serial=None, file=None):
    if serial is not None:
        url = f"ftdi://::{serial}/1"
    ft_ee = FtdiEeprom()
    ft_ee.open(url, model=MODEL)
    print(hexdump(ft_ee.data, full=True), file=file or sys.stdout)
    ft_ee.close()


def find_devices(url="ftdi://ftdi:232h:/1"):
    locations = []
    devices = Ftdi.list_devices(url)
    for dev in devices:
        vid, pid, bus, address, sn, _, desc = dev[0]
        locations.append((vid, pid, bus, address))

    return locations


def find_serial_numbers(url="ftdi://ftdi:232h:/1"):
    serials = []
    devices = Ftdi.list_devices(url)
    for dev in devices:
        vid, pid, bus, address, sn, _, desc = dev[0]
        print(
            f"VID:PID: {vid:04X}:{pid:04X}, Bus: {bus}, Address: {address}, Serial: {sn}, Desc: {desc}"
        )
        if sn:
            serials.append(sn)
    return serials


def configure_all_ftdis(force=True, dry_run=True, dump=False):
    devices = find_devices()
    for ix, dev in enumerate(devices):
        vid, pid, bus, address = dev
        if vid != 0x0403 or pid != 0x6014:
            print(f"Device: {dev} is not FTDI FT232H. Skipping...")
            continue
        url = f"ftdi://:232h:{bus:x}:{address:x}/1"
        new_serial = f"DT{ix:02d}"
        print(f"Configuring device {dev} with new serial: {new_serial}")
        configure_ftdi(
            url=url,
            manufacturer=MANUFACTURER,
            product=PRODUCT,
            serial=new_serial,
            force=force,
            dry_run=dry_run,
        )
        if dump:
            print(f"Dumping EEPROM contents for device {dev}")
            dump_ee_contents(url=url)



if __name__ == "__main__":
    # configure_all_ftdis(force=True, dry_run=True, dump=False)
    serials = find_serial_numbers()

    print(f"Found serials: {serials}")
    for sn in serials:
        print(f"Serial: {sn}")
        dump_ee_contents(serial=sn)
