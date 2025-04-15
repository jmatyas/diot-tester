import argparse
import os
import time
from typing import Dict, List, Optional, Union

from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.i2c import I2C as _I2C
from adafruit_pca9685 import PCA9685
from busio import I2C
from pyftdi.eeprom import FtdiEeprom

from chips.eeprom_24aa025e48 import EEPROM24AA02E48
from chips.lm75 import LM75
from chips.mcp3221 import MCP3221
from chips.pca9544 import PCA9544A

# it corresponds to "93C46" chip; possible values are "93C56" and "93C66"
# but on DIOT cards we use "93C46" (0x46)
FTDI_EEPROM_CHIP_TYPE = 0x46


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


class Channel:
    """Represents a single load channel with temperature monitoring and power control."""

    def __init__(self, pwm_channel, temperature_sensor, max_power=None):
        if max_power is None:
            max_power = 5  # 5 Watts
        self.pwm_channel = pwm_channel
        self.temperature_sensor = temperature_sensor
        self.max_power = max_power

    # === LM75 properties ===
    @property
    def temperature(self) -> float:
        """Get the current temperature reading from the sensor"""
        return self.temperature_sensor.temperature

    @property
    def hysteresis(self) -> float:
        """Get the hysteresis temperature setting"""
        return self.temperature_sensor.temperature_hysteresis

    @hysteresis.setter
    def hysteresis(self, value: float) -> None:
        """Set the hysteresis temperature"""
        self.temperature_sensor.temperature_hysteresis = value

    @property
    def ot_shutdown(self) -> float:
        """Get the over-temperature shutdown setting"""
        return self.temperature_sensor.temperature_shutdown

    @ot_shutdown.setter
    def ot_shutdown(self, value: float) -> None:
        """Set the over-temperature shutdown threshold"""
        self.temperature_sensor.temperature_shutdown = value

    # === PCA9685 properties ===
    @property
    def frequency(self) -> float:
        """Get the PWM frequency"""
        return self.pwm_channel.frequency

    @property
    def load_power(self) -> float:
        """Get the current load power in Watts"""
        return (
            self.pwm_channel.duty_cycle / 0xFFFF * self.max_power
        )  # FIXME: check if this is correct

    @load_power.setter
    def load_power(self, power: float) -> None:
        """Set the load power in Watts"""
        if power > self.max_power:
            raise ValueError(f"Power must be less than {self.max_power} W")

        self.pwm_channel.duty_cycle = int(power / self.max_power * 0xFFFF)

    def set_configuration(
        self, hysteresis: float = None, ot_shutdown: float = None, power: float = None
    ) -> None:
        """Configure multiple parameters at once"""
        if hysteresis is not None:
            self.hysteresis = hysteresis
        if ot_shutdown is not None:
            self.ot_shutdown = ot_shutdown
        if power is not None:
            self.load_power = power

    def report(self) -> Dict[str, float]:
        """Get a report of all channel parameters"""
        return {
            "temperature": self.temperature,
            "hysteresis": self.hysteresis,
            "ot_shutdown": self.ot_shutdown,
            "load_power": self.load_power,
        }


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
        serial: str = None,
    ) -> None:
        """Initialize the DIOT Card controller.

        Args:
            url: FTDI URL to connect to
            frequency: I2C bus frequency
            ot_shutdown: Default over-temperature shutdown threshold
            hysteresis: Default hysteresis value
            serial: FTDI serial number in format "DTxx" where xx is 0-8

        """
        if serial is not None:
            url = f"ftdi://::{serial}/1"
        # needed for '_I2C' from pyFTDI to work if there are more than one FTDI
        # devices connected to the system
        os.environ["BLINKA_FT232H"] = url

        self.init_i2c(frequency=frequency)
        self.init_devices()
        self.init_config(ot_shutdown, hysteresis)

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

        self.diot_conn_lm75s = [
            LM75(self.i2c_buses[3], device_address=0x49),  # P6 connector
            LM75(self.i2c_buses[3], device_address=0x4A),  # P1 connector
        ]

    def init_config(self, ot_shutdown=80, hysteresis=75) -> None:
        """Initialize card with default settings"""
        # enable auto-increment so we can write/read registers using CP structures
        for pwm in self.pwm_chips:
            read_mode1 = pwm.mode1_reg
            pwm.mode1_reg = read_mode1 | 0x20

        for channel in self.load_channels:
            channel.set_configuration(ot_shutdown=ot_shutdown, hysteresis=hysteresis)

    @property
    def card_id(self) -> Optional[str]:
        """Get the card identifier from serial number"""
        return self.serial_id

    @property
    def eui48(self) -> List[int]:
        """Get the EEPROM EUI-48 address"""
        return self.eeprom.eui48

    @property
    def eui64(self) -> List[int]:
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

    def scan(self, write=False) -> List[int]:
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

    def get_measurements(self) -> Dict[str, Union[float, Dict[int, Dict[str, float]]]]:
        """Get all measurements from the card"""
        channel_reports = {}
        for i, channel in enumerate(self.load_channels):
            channel_reports[i] = channel.report()

        return {
            "voltage": self.voltage,
            "current": self.current,
            "channels": channel_reports,
        }

    def set_all_load_power(self, power: float) -> None:
        """Set the same load power for all channels"""
        for channel in self.load_channels:
            channel.load_power = power

    def shutdown_all_loads(self) -> None:
        """Turn off all loads"""
        self.set_all_load_power(0)


class CrateController:
    """Controller for managing multiple DIOT cards in a crate."""

    def __init__(
        self,
        serial_numbers: List[str] = None,
        frequency: int = 100000,
        ot_shutdown: float = 80,
        hysteresis: float = 75,
    ) -> None:
        """Initialize the CrateController with a list of DIOT card serial numbers.

        Args:
            serial_numbers: List of FTDI serial numbers in format "DTxx" where xx is 0-8
            frequency: I2C bus frequency
            ot_shutdown: Default over-temperature shutdown threshold
            hysteresis: Default hysteresis value

        """
        self.cards = {}
        if serial_numbers:
            for serial in serial_numbers:
                self.add_card(serial, frequency, ot_shutdown, hysteresis)

    def add_card(
        self,
        serial: str,
        frequency: int = 100000,
        ot_shutdown: float = 80,
        hysteresis: float = 75,
    ) -> None:
        """Add a card to the controller by serial number"""
        if not serial.startswith("DT"):
            raise ValueError("Serial number must start with 'DT'")

        try:
            card = DIOTCard(
                serial=serial,
                frequency=frequency,
                ot_shutdown=ot_shutdown,
                hysteresis=hysteresis,
            )
            self.cards[serial] = card
            print(f"Card {serial} connected successfully")
        except Exception as e:
            print(f"Failed to connect to card {serial}: {str(e)}")

    def get_card(self, serial: str) -> DIOTCard:
        """Get a specific card by serial number"""
        if serial not in self.cards:
            raise KeyError(f"Card with serial {serial} not found")
        return self.cards[serial]

    def get_all_cards(self) -> Dict[str, DIOTCard]:
        """Get all connected cards"""
        return self.cards

    def shutdown_all_loads(self) -> None:
        """Turn off all loads on all cards"""
        for card in self.cards.values():
            card.shutdown_all_loads()

    def get_all_measurements(self) -> Dict[str, Dict]:
        """Get measurements from all cards"""
        measurements = {}
        for serial, card in self.cards.items():
            measurements[serial] = card.get_measurements()
        return measurements


def main():
    """Simple command-line interface for DIOT crate testing.
    Designed to be easy to use for physicists with minimal programming knowledge.
    """
    # Create argument parser for command line interface
    parser = argparse.ArgumentParser(description="DIOT Crate Testing Tool")

    # Basic commands
    parser.add_argument(
        "--list-cards", action="store_true", help="List all available DIOT cards"
    )
    parser.add_argument(
        "--monitor", action="store_true", help="Monitor temperatures and voltages"
    )
    parser.add_argument(
        "--set-load",
        nargs=3,
        metavar=("CARD", "CHANNEL", "POWER"),
        help="Set load power for a specific channel (e.g., DT01 5 1.5)",
    )
    parser.add_argument(
        "--set-all",
        nargs=2,
        metavar=("CARD", "POWER"),
        help="Set same load power for all channels on a card (e.g., DT01 1.5)",
    )
    parser.add_argument("--shutdown", action="store_true", help="Shutdown all loads")
    parser.add_argument(
        "--set-ot-threshold",
        nargs=3,
        metavar=("CARD", "CHANNEL", "TEMP"),
        help="Set over-temperature threshold for a channel (e.g., DT01 5 85)",
    )
    parser.add_argument(
        "--set-hysteresis",
        nargs=3,
        metavar=("CARD", "CHANNEL", "TEMP"),
        help="Set temperature hysteresis for a channel (e.g., DT01 5 75)",
    )

    args = parser.parse_args()

    # Default to list if no args provided
    if len(os.sys.argv) == 1:
        print("DIOT Crate Testing Tool")
        print("----------------------")
        print("Available commands:")
        print("  --list-cards           : List all available DIOT cards")
        print("  --monitor              : Monitor temperatures and voltages")
        print("  --set-load CARD CH POW : Set load power for a specific channel")
        print("  --set-all CARD POW     : Set same load power for all channels")
        print("  --shutdown             : Shutdown all loads")
        print("  --set-ot-threshold CARD CH TEMP : Set over-temperature threshold")
        print("  --set-hysteresis CARD CH TEMP   : Set temperature hysteresis")
        print("\nFor more detailed information, run: python diot_tester.py --help")
        return

    # Find all connected cards (DTxx serial numbers)
    import pyftdi.ftdi

    available_cards = []
    try:
        for dev in pyftdi.ftdi.Ftdi.list_devices():
            url, desc, serial = dev
            if serial and serial.startswith("DT"):
                available_cards.append(serial)
    except:
        print("No FTDI devices found. Make sure FTDI drivers are installed.")
        return

    if not available_cards:
        print("No DIOT cards (with DTxx serial numbers) found.")
        return

    # List cards if requested
    if args.list_cards:
        print(f"Found {len(available_cards)} DIOT cards:")
        for serial in available_cards:
            print(f"  - Card: {serial}")
        return

    # Create the crate controller with all available cards
    crate = CrateController(available_cards)

    # Set load power for a specific channel
    if args.set_load:
        card_serial, channel_str, power_str = args.set_load
        try:
            channel = int(channel_str)
            power = float(power_str)
            card = crate.get_card(card_serial)
            channel_obj = card.get_channel(channel)
            channel_obj.load_power = power
            print(
                f"Set load power for card {card_serial}, channel {channel} to {power} W"
            )
        except Exception as e:
            print(f"Error setting load power: {str(e)}")

    # Set load power for all channels on a card
    if args.set_all:
        card_serial, power_str = args.set_all
        try:
            power = float(power_str)
            card = crate.get_card(card_serial)
            card.set_all_load_power(power)
            print(f"Set all channels on card {card_serial} to {power} W")
        except Exception as e:
            print(f"Error setting load power: {str(e)}")

    # Shutdown all loads
    if args.shutdown:
        crate.shutdown_all_loads()
        print("All loads shut down.")

    # Set over-temperature threshold
    if args.set_ot_threshold:
        card_serial, channel_str, temp_str = args.set_ot_threshold
        try:
            channel = int(channel_str)
            temp = float(temp_str)
            card = crate.get_card(card_serial)
            channel_obj = card.get_channel(channel)
            channel_obj.ot_shutdown = temp
            print(
                f"Set OT threshold for card {card_serial}, channel {channel} to {temp}°C"
            )
        except Exception as e:
            print(f"Error setting OT threshold: {str(e)}")

    # Set temperature hysteresis
    if args.set_hysteresis:
        card_serial, channel_str, temp_str = args.set_hysteresis
        try:
            channel = int(channel_str)
            temp = float(temp_str)
            card = crate.get_card(card_serial)
            channel_obj = card.get_channel(channel)
            channel_obj.hysteresis = temp
            print(
                f"Set hysteresis for card {card_serial}, channel {channel} to {temp}°C"
            )
        except Exception as e:
            print(f"Error setting hysteresis: {str(e)}")

    # Monitor temperatures and voltages
    if args.monitor:
        try:
            print("Monitoring DIOT crate. Press Ctrl+C to stop.")
            print("---------------------------------------")
            while True:
                for serial, card in crate.get_all_cards().items():
                    print(f"\nCard: {serial}")
                    print(f"Voltage: {card.voltage:.3f} V")
                    print(f"Current: {card.current:.3f} A")
                    print("Temperatures:")

                    for i, channel in enumerate(card.load_channels):
                        if i % 4 == 0 and i > 0:
                            print()  # Add newline every 4 channels for readability
                        print(
                            f"CH{i}: {channel.temperature:.1f}°C ({channel.load_power:.2f}W) ",
                            end="",
                        )
                    print("\n")

                time.sleep(1)
                # Clear screen for next update
                print("\033c", end="")
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")


if __name__ == "__main__":
    main()
