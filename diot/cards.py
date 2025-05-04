import os

from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.i2c import I2C as _I2C
from adafruit_pca9685 import PCA9685
from busio import I2C
from pyftdi.eeprom import FtdiEeprom

from chips.eeprom_24aa025e48 import EEPROM24AA02E48
from chips.lm75 import LM75
from chips.mcp3221 import MCP3221
from chips.pca9544 import PCA9544A
from diot.channel import Channel, SensorChannel
from diot.utils.i2c_utils import make_i2c_graph

# it corresponds to "93C46" chip; possible values are "93C56" and "93C66"
# but on DIOT cards we use "93C46" (0x46)
FTDI_EEPROM_CHIP_TYPE = 0x46

SOFT_OT_THRESHOLD = 5  # degrees Celsius


class DIOTCard(I2C):
    """Controller for a single DIOT card in the crate.
    Each card has 17 load channels (16 regular + 1 auxiliary) with temperature sensors.
    """

    scan_blacklist = [0x70]

    def __init__(
        self,
        url: str = "ftdi://ftdi:232h:/1",
        frequency: int = 100000,
        ot_shutdown: float = 80,
        hysteresis: float = 75,
        serial: str | None = None,
    ) -> None:
        """Initialize the DIOT Card controller.

        Args:
            url: FTDI URL to connect to
            frequency: I2C bus frequency
            ot_shutdown: Default over-temperature shutdown threshold
            hysteresis: Default hysteresis value
            serial: FTDI serial number in format "DTxx" where xx is 0-8

        """

        # TODO: check if providing serial number overrides url and what happens
        # when no serial number is provided and multiple FTDI devices are
        # connected to the system
        if serial is not None:
            url = f"ftdi://::{serial}/1"
        # needed for '_I2C' from pyFTDI to work if there are more than one FTDI
        # devices connected to the system
        os.environ["BLINKA_FT232H"] = url

        # No reinitialization is needed in case the OT event happens - power is
        # turned off only of heaters (and I2C buffers), and not of the ICs
        self.init_i2c(frequency=frequency)
        self.init_devices()
        self.init_config(ot_shutdown, hysteresis)
        self._initialized = True

    def init_i2c(self, frequency: int = 100000) -> None:
        self.deinit()
        # this is workaround; it seems that without setting the frequency explicitly
        # the FTDI device is unable to communicate with devices on I2C bus every
        # second time the program is run (it's rather not a problem with the device,
        # but with the library or configuration). From the scope it seems that
        # FTDI produces START condition, but no data is sent afterwards (it doesn't
        # produce clock..., however, STOP condition is sent).
        self._i2c = _I2C(frequency=frequency)
        ftdi = self._i2c._i2c.ftdi
        ftdi.set_frequency(frequency)
        self.ftdi_ee = FtdiEeprom()

        # without below, pyFTDI's FtdiEeprom gets EEPROM size that by default is
        # set in code to 256 bytes, wheras the EEPROM on DIOT card is 128 bytes.
        # Size of 256 bytes results in erroneous reading of the EEPROM contents,
        # specifically the user area, which is used to store the serial number
        # and product and manufacturer names...
        self.ftdi_ee._chip = FTDI_EEPROM_CHIP_TYPE
        self.ftdi_ee.connect(ftdi)

        self.serial_id = self.ftdi_ee.serial

    def init_devices(self) -> None:
        # 2 EEPROM to EEM0
        self.eeprom = EEPROM24AA02E48(self, address=0x50)

        self.i2c_mux = PCA9544A(self, address=0x70)
        self.i2c_buses = [
            self.i2c_mux[0],
            self.i2c_mux[1],
            self.i2c_mux[2],
            self.i2c_mux[3],
        ]

        # Mux channels 0 and 1 swapped
        self.lm75s = [
            LM75(self.i2c_buses[1], device_address=0x48 + addr) for addr in range(8)
        ] + [LM75(self.i2c_buses[0], device_address=0x48 + addr) for addr in range(8)]

        self.i_monitor = MCP3221(
            self.i2c_buses[2], device_address=0x4D, reference_voltage=3.3
        )
        self.v_monitor = MCP3221(
            self.i2c_buses[3], device_address=0x4D, reference_voltage=3.3
        )

        self.pwm_chips = [
            PCA9685(self.i2c_buses[2], address=0x40),
            PCA9685(self.i2c_buses[2], address=0x41),
        ]

        self.aux_lm75 = LM75(self.i2c_buses[3], device_address=0x48)
        self.aux_load = self.pwm_chips[1].channels[0]

        self.load_channels = [
            Channel(self.pwm_chips[0].channels[i], self.lm75s[i]) for i in range(16)
        ] + [Channel(self.aux_load, self.aux_lm75, max_power=3)]

        self.diot_conn_channels = [
            SensorChannel(LM75(self.i2c_buses[3], device_address=0x49)),  # P6 connector
            SensorChannel(LM75(self.i2c_buses[3], device_address=0x4A)),  # P1 connector
        ]

        # don't use the 3.3V channel for load power
        self.max_load_power = sum([ch.max_power for ch in self.load_channels[:-1]])

    def init_config(self, ot_shutdown: float = 80, hysteresis: float = 75) -> None:
        """Initialize card with default settings"""
        # enable auto-increment so we can write/read registers using CP structures
        for pwm in self.pwm_chips:
            read_mode1 = pwm.mode1_reg
            pwm.mode1_reg = read_mode1 | 0x20

        for channel in self.load_channels + self.diot_conn_channels:
            channel.set_configuration(ot_shutdown=ot_shutdown, hysteresis=hysteresis)

        # FIXME: now it is assumed that software OT shutdown is set to SOFT_OT_THRESHOLD
        # degrees below the hardware shutdown threshold.
        self._soft_ot_shutdown = ot_shutdown - SOFT_OT_THRESHOLD
        self._soft_hysteresis = hysteresis - SOFT_OT_THRESHOLD

    @property
    def card_id(self) -> str:
        """Get the card identifier from serial number"""
        return self.serial_id

    @property
    def eui48(self) -> list[int]:
        """Get the EEPROM EUI-48 address"""
        return self.eeprom.eui48

    @property
    def eui64(self) -> list[int]:
        """Get the EEPROM EUI-64 address"""
        return self.eeprom.eui64

    @property
    def current(self) -> float:
        """Get the current reading in Amperes"""
        # IN195 senses current on 0.005 Ohm resistor and amplifies it by 100 V/V,
        # which results in 0.5 V/A of 'transimpedance'.
        voltage_reading = self.i_monitor.voltage
        return voltage_reading / 0.5

    @property
    def voltage(self) -> float:
        """Get the voltage reading in Volts"""
        # there is a voltage divider of 1/4 on the board, so the voltage
        # reading is 4 times lower than the actual voltage
        voltage_reading = self.v_monitor.voltage
        return voltage_reading * 4

    def scan(self, write: bool = False) -> list[int]:
        """Scan for I2C devices on the bus"""
        # Override method from busio.i2c.scan, so it accepts one positional
        # argument
        return self._i2c.scan(write)

    def print_i2c_tree(self) -> None:
        """Print the I2C device tree for debugging"""
        # on each I2C bus there is EEPROM detected. it's due to the fact, that
        # the EEPROMs are connected BEFORE the I2C MUX so, they are always detected
        # (they just respond to polling on their address)
        for ix, bus in enumerate([self, *self.i2c_buses]):
            bus_name = "I2C Shared Bus" if ix == 0 else f"I2C Bus {ix}"
            detected = bus.scan(write=True)
            print(f"{bus_name}:")
            print(make_i2c_graph(detected))

    def set_pwm_frequency(self, chip_no: int, frequency: int) -> None:
        """Set the PWM frequency for a specific PWM chip"""
        if frequency < 24 or frequency > 1526:
            raise ValueError("Frequency must be between 24 and 1526 Hz")
        self.pwm_chips[chip_no].frequency = frequency

    def get_channel(self, channel_index: int) -> Channel:
        """Get a specific load channel by index (0-16)"""
        if not 0 <= channel_index < len(self.load_channels):
            raise ValueError(
                f"Channel index must be between 0 and {len(self.load_channels) - 1}"
            )
        return self.load_channels[channel_index]

    def set_all_load_power(self, power: float) -> None:
        """Set the same load power for all channels"""
        for channel in self.load_channels[:-1]:
            channel.load_power = power

    def shutdown_all_loads(self) -> None:
        """Turn off all loads"""
        self.set_all_load_power(0)

    def report(self):
        """Get a report of all channel parameters"""
        channels_reports = []
        for channel in self.load_channels + self.diot_conn_channels:
            rep = channel.report()
            rep["ot_ev"] = rep["temperature"] >= self._soft_ot_shutdown
            channels_reports.append(rep)

        rep = {
            "card_serial": self.card_id,
            "voltage": self.voltage,
            "current": self.current,
            "channels": channels_reports,
        }
        return rep
