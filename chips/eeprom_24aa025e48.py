# SPDX-FileCopyrightText: 2023 Mikołaj Sowiński for TechnoSystem sp. z o.o.
# SPDX-FileCopyrightText: 2023 Jakub Matyas for Warsaw University of Technology
#
# SPDX-License-Identifier: MIT

import time
from typing import List

from adafruit_bus_device import i2c_device
from busio import I2C


class EE24AA02XEXX:
    LENGTH = 1 << 8
    DEFAULT_PAGESIZE = 8

    def __init__(
        self,
        bus_device: I2C,
        address: int,
        page_size: int = DEFAULT_PAGESIZE,
    ) -> None:
        self._device = i2c_device.I2CDevice(bus_device, address)
        self.page_size = page_size

    @property
    def eui48(self) -> List[int]:
        read_buffer = bytearray(6)
        write_buffer = bytearray([0xFA])
        with self._device as i2c:
            i2c.write_then_readinto(write_buffer, read_buffer)
        return [int(x) for x in read_buffer]

    @property
    def eui64(self) -> List[int]:
        read_buffer = bytearray(8)
        write_buffer = bytearray([0xF8])
        with self._device as i2c:
            i2c.write_then_readinto(write_buffer, read_buffer)
        return [int(x) for x in read_buffer]

    @property
    def contents(self) -> List[int]:
        read_buffer = bytearray(self.LENGTH)
        write_buffer = bytearray([0x0])
        with self._device as i2c:
            i2c.write_then_readinto(write_buffer, read_buffer)
        return [int(x) for x in read_buffer]

    def _poll(self, timeout=None):
        t = time.monotonic()
        while True:
            with self._device as i2c:
                try:
                    i2c.__probe_for_device()
                    return
                except OSError:
                    pass
            if timeout:
                if t + timeout > time.monotonic():
                    raise TimeoutError

    @contents.setter
    def contents(self, value: List[int]) -> None:
        with self._device as i2c:
            for i in range(0, len(value), self.page_size):
                write_buffer = bytearray([i, *(value[i : i + self.page_size])])
                i2c.write(write_buffer)
                self._poll()


class EEPROM24AA025E48(EE24AA02XEXX):
    LENGTH = 1 << 8
    DEFAULT_PAGESIZE = 16

    def __init__(
        self, bus_device: I2C, address: int, page_size: int = DEFAULT_PAGESIZE
    ) -> None:
        super().__init__(bus_device=bus_device, address=address, page_size=page_size)

    @property
    def eui64(self) -> List[int]:
        # see EUI-64 support using the 24AAXXXE48
        # on page 14 in https://ww1.microchip.com/downloads/en/devicedoc/20002124g.pdf
        return [*self.eui48[:3], 0xFF, 0xFE, *self.eui48[3:]]


class EEPROM24AA02E48(EE24AA02XEXX):
    LENGTH = 1 << 8
    DEFAULT_PAGESIZE = 8

    def __init__(
        self, bus_device: I2C, address: int, page_size: int = DEFAULT_PAGESIZE
    ) -> None:
        super().__init__(bus_device=bus_device, address=address, page_size=page_size)

    @property
    def eui64(self) -> List[int]:
        # see EUI-64 support using the 24AAXXXE48
        # on page 14 in https://ww1.microchip.com/downloads/en/devicedoc/20002124g.pdf
        return [*self.eui48[:3], 0xFF, 0xFE, *self.eui48[3:]]
