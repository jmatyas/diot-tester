from adafruit_bus_device import i2c_device 

from busio import I2C

MCP3221_DEFAULT_ADDRESS = 0x4D
MCP3221_MAX_SUPPLY_VOLTAGE = 5.5
MCP3221_MIN_SUPPLY_VOLTAGE = 2.7

_BUFFER = bytearray(2)
class MCP3221:
    def __init__(self, i2c_bus: I2C, device_address: int = MCP3221_DEFAULT_ADDRESS, reference_voltage: float = 3.3):
        self.i2c_device = i2c_device.I2CDevice(i2c_bus, device_address, probe=True)
        if MCP3221_MIN_SUPPLY_VOLTAGE <= reference_voltage <= MCP3221_MAX_SUPPLY_VOLTAGE:
            self._reference_voltage = reference_voltage
        else:
            raise ValueError("Reference voltage must be between 2.7V and 5.5V.")

    @property
    def reference_voltage(self) -> float:
        """The voltage level that ADC signals are compared to.
        An ADC value of 4095 will equal `reference_voltage`"""
        return self._reference_voltage

    def _read_data(self):
        with self.i2c_device as device:
            device.readinto(_BUFFER)
            return ((_BUFFER[0] << 8) | _BUFFER[1])# & 0xFFF

    @property
    def voltage(self) -> float:
        """Returns the value of an ADC in volts."""
        raw_reading = self._read_data()
        return ((raw_reading & 0xFFF) / 4096) * self.reference_voltage