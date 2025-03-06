# SPDX-FileCopyrightText: 2023 Jakub Matyas for TechnoSystem sp. z o.o.
#
# SPDX-License-Identifier: MIT

import adafruit_bus_device.i2c_device as i2cdevice
from adafruit_register.i2c_bit import RWBit
from adafruit_register.i2c_bits import ROBits, RWBits
from adafruit_register.i2c_struct import ROUnaryStruct, UnaryStruct
from busio import I2C

LM75_DEFAULT_ADDRESS = 0x48
LM75_REGISTER_TEMP = 0x00
LM75_REGISTER_CONFIG = 0x01
LM75_REGISTER_THYST = 0x02
LM75_REGISTER_TOS = 0x03
LM75_REGISTER_PRODID = 0x07


class LM75:
    _temperature = ROUnaryStruct(LM75_REGISTER_TEMP, ">h")
    _shutdown_en = RWBit(LM75_REGISTER_CONFIG, 0, 1)
    mode = RWBit(LM75_REGISTER_CONFIG, 1, 1)
    os_polarity = RWBit(LM75_REGISTER_CONFIG, 2, 1)
    _fault_queue = RWBits(2, LM75_REGISTER_CONFIG, 3, 1)
    _temp_shutdown = UnaryStruct(LM75_REGISTER_TOS, ">h")
    _temp_hysteresis = UnaryStruct(LM75_REGISTER_THYST, ">h")
    _prodid = ROBits(7, LM75_REGISTER_PRODID, 0, 1)

    def __init__(
        self, i2c_bus: I2C, device_address: int = LM75_DEFAULT_ADDRESS
    ) -> None:
        self.i2c_device = i2cdevice.I2CDevice(i2c_bus, device_address)

    @property
    def temperature(self) -> float:
        return (self._temperature >> 7) * 0.5

    @property
    def temperature_hysteresis(self) -> float:
        return (self._temp_hysteresis >> 7) * 0.5

    @temperature_hysteresis.setter
    def temperature_hysteresis(self, value: float) -> None:
        self._temp_hysteresis = int(value * 2) << 7

    @property
    def temperature_shutdown(self) -> float:
        return (self._temp_shutdown >> 7) * 0.5

    @temperature_shutdown.setter
    def temperature_shutdown(self, value: float) -> None:
        self._temp_shutdown = int(value * 2) << 7

    @property
    def faults_to_alert(self) -> int:
        return self._fault_queue

    @faults_to_alert.setter
    def faults_to_alert(self, value: int) -> None:
        if value not in (1, 2, 4, 6):
            raise ValueError(
                "faults_to_alert must be one of the following: [1, 2, 4, 6] "
            )
        self._fault_queue = value

    @property
    def product_id(self) -> int:
        return self._prodid

    @property
    def shutdown_en(self) -> int:
        return self._shutdown_en

    @shutdown_en.setter
    def shutdown_en(self, value: bool) -> None:
        val = 1 if value else 0
        self._shutdown_en = val
