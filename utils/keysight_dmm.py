"""Keysight 34461A Digital Multimeter Controller.

This module provides a class for controlling Keysight 34461A Digital Multimeter
via VISA (SCPI commands).

Supports:
- DC/AC voltage measurements
- DC/AC current measurements
- Resistance measurements
- Configurable measurement ranges
- Auto-ranging
- Averaging and filtering
"""

import argparse
import logging
import time
from enum import Enum

import pyvisa

logger = logging.getLogger(__name__)



class MeasurementMode(Enum):
    """Supported measurement modes for the DMM."""

    VOLT_DC = "VOLT"
    # VOLT_AC = "VOLT:AC"
    # CURR_DC = "CURR"
    # CURR_AC = "CURR:AC"
    # RES = "RES"
    # FRES = "FRES"  # 4-wire resistance


class Keysight34461A:
    """Class to control Keysight 34461A Digital Multimeter.

    Provides methods for configuring and taking measurements with
    the Keysight 34461A 6½ digit DMM using SCPI commands over VISA.
    """

    def __init__(self, address: str, timeout_s: float = 5):
        """Initialize the DMM connection.

        Args:
            address (str): IP address or VISA resource name
                e.g., '192.168.1.100' for network connection
                or 'TCPIP::192.168.1.100::INSTR' for full VISA resource
            timeout_s (float): Connection timeout in seconds
        """
        self.address = address
        self.timeout = timeout_s * 1000  # Convert to milliseconds
        self.instrument = None
        self.connect()

    def connect(self):
        """Establish connection to the DMM."""
        rm = pyvisa.ResourceManager()
        try:
            # Handle both bare IP addresses and full VISA resource names
            if "::" not in self.address:
                resource_name = f"TCPIP::{self.address}::INSTR"
            else:
                resource_name = self.address

            self.instrument = rm.open_resource(resource_name)
            self.instrument.timeout = self.timeout
            idn = self.idn().strip()
            logger.info(f"Connected to: {idn}")

            # Check if it's a Keysight/Agilent device
            if "Keysight" not in idn and "Agilent" not in idn:
                logger.warning("Connected device may not be a Keysight/Agilent DMM")
        except Exception as e:
            logger.error(f"Connection failed: {e}", exc_info=True)
            raise e

    def disconnect(self):
        """Close the connection to the DMM."""
        if self.instrument:
            self.instrument.close()
            self.instrument = None
            logger.info("Connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic connection closing."""
        self.disconnect()

    def write(self, command: str):
        """Send a command to the DMM."""
        self.instrument.write(command)

    def query(self, command: str) -> str:
        """Query the DMM and return response."""
        return self.instrument.query(command)

    def idn(self) -> str:
        """Get the identification string of the DMM."""
        return self.query("*IDN?")

    def reset(self):
        """Reset the DMM to default settings."""
        self.write("*RST")
        logger.info("DMM reset to default settings")

    def clear_status(self):
        """Clear the status registers."""
        self.write("*CLS")

    def query_opc(self) -> str:
        """Query operation complete status."""
        return self.query("*OPC?")

    def wait_for_opc(self, timeout: float = 5):
        """Wait for operation to complete."""
        t = time.monotonic()
        while int(self.query_opc()) != 1:
            if time.monotonic() - t > timeout:
                raise TimeoutError("Operation timed out")
            time.sleep(0.1)

    # ==========================================================================
    # Configuration Methods
    # ==========================================================================

    def configure(
        self,
        mode: MeasurementMode = MeasurementMode.VOLT_DC,
        range_value: float | None = None,
        resolution: float | None = None,
    ):
        """Configure the DMM for a specific measurement type.

        Args:
            mode (MeasurementMode): Measurement mode (VOLT_DC, CURR_DC, etc.)
            range_value (float, optional): Measurement range. If None, uses auto-range.
                For VOLT_DC: 0.1, 1, 10, 100, 1000 V
                For CURR_DC: 0.0001, 0.001, 0.01, 0.1, 1, 3 A
            resolution (float, optional): Measurement resolution in same units as range.
                If None, uses default resolution for the range.

        Examples:
            # Auto-ranging DC voltage
            dmm.configure(MeasurementMode.VOLT_DC)

            # Fixed 10V range with default resolution
            dmm.configure(MeasurementMode.VOLT_DC, range_value=10)

            # Fixed 10V range with 0.001V resolution
            dmm.configure(MeasurementMode.VOLT_DC, range_value=10, resolution=0.001)
        """
        mode_str = mode.value

        if range_value is None:
            # Auto-ranging
            cmd = f"CONF:{mode_str} AUTO"
        elif resolution is None:
            # Fixed range, default resolution
            cmd = f"CONF:{mode_str} {range_value}"
        else:
            # Fixed range and resolution
            cmd = f"CONF:{mode_str} {range_value},{resolution}"

        self.write(cmd)
        logger.debug(
            f"Configured for {mode_str}, range={range_value}, res={resolution}"
        )

    def set_number_of_samples(self, count: int = 1):
        """Set the number of samples to take every trigger (number of measurements).

        Theoretically, up to 1,000,000 samples can be taken per trigger,
        but practical limits depend on memory which for 34461A is about 10,000 samples.

        Args:
            count (int): Number of samples (1 to 1e4). Default is 1.
        """
        if not (1 <= count <= 1e4):
            raise ValueError("Sample count must be between 1 and 10,000")
        self.write(f"SAMP:COUN {count}")
        logger.debug(f"Number of samples set to: {count}")

    def set_auto_range(self, enable: bool = True):
        """Enable or disable auto-ranging for the current function.

        Args:
            enable (bool): True to enable auto-range, False to disable
        """
        state = "ON" if enable else "OFF"
        self.write(f"SENS:VOLT:RANG:AUTO {state}")
        logger.debug(f"Auto-range: {state}")

    def set_range(self, range_value: float):
        """Set the measurement range for the current function.

        Args:
            range_value (float): Range value in units appropriate for current function
        """
        self.write(f"SENS:VOLT:RANG {range_value}")
        logger.debug(f"Range set to: {range_value}")

    def set_nplc(self, nplc: float):
        """Set the integration time in Number of Power Line Cycles.

        Args:
            nplc (float): Integration time (0.001 to 100 PLC)
                Lower values = faster measurements, higher noise
                Higher values = slower measurements, lower noise
                Typical values: 0.02, 0.2, 1, 10, 100
        """
        if not 0.001 <= nplc <= 100:
            raise ValueError("NPLC must be between 0.001 and 100")
        self.write(f"SENS:VOLT:NPLC {nplc}")
        logger.debug(f"NPLC set to: {nplc}")

    # ==========================================================================
    # Measurement Methods
    # ==========================================================================
    def r(self, max_reading: int) -> list[float]:
        """Reads and erases all measurements from reading memory up to the maximum specified.

        The measurements are read and erased from the reading memory starting
        with the oldest measurement first.

        Args:
            max_reading (int): Maximum expected measurements to read. Must be positive
                and less than 1e4 (10,000). This is just to prevent user from setting
                an excessively high value by mistake. But it's possible to handle
                more readings by calling this method multiple times during long measurements.
        """
        if max_reading <= 0:
            raise ValueError("max_reading must be positive")
        if max_reading > 1e4:
            raise ValueError("max_reading too large")

        # TODO: do it better...
        result = self.query(f"R? {max_reading}").strip()
        ndigits = int(result[1])
        _length_of_data = int(result[2 : 2 + ndigits])
        results = result[2 + ndigits :].split(",")
        return [float(v) for v in results]

    def read(self) -> list[float]:
        """Starts a new set of measurements waits for completion and returns measurements.

        Sending the READ? command is similar to sending INITiate command followed
        by a FETCH? command. However, FETCH? doesn't erase the readings from the reading memory,
        while READ? does.


        Returns:
            float: Measurement value

        Note:
            This performs a complete measurement cycle: trigger, wait, fetch
        """
        result = self.query("READ?").strip()
        return [float(v) for v in result.split(",")]

    def fetch(self) -> float:
        """Fetch the last measurement without triggering a new one.

        Returns:
            float: Last measurement value
        """
        result = self.query("FETCH?")
        return float(result.strip())

    def get_number_of_measurement_points(self) -> int:
        """Get the number of measurement points currently stored in reading memory.

        Returns:
            int: Number of measurement points
        """
        result = self.query("DATA:POIN?")
        return int(result.strip())

    def get_measurement(self) -> list[float]:
        """Get a measurement value (primary interface method).

        Returns:
            float: Measurement value

        Note:
            This is the main method to use for getting measurements.
            It triggers a new measurement and returns the result.
        """
        return self.read()

    def measure_voltage_dc(self, range_value: float | None = None) -> float:
        """Convenience method to measure DC voltage.

        Sets all the parameters to default for quick DC voltage measurement, triggering a single reading.
        and returns the measured value.

        Args:
            range_value (float, optional): Voltage range. None for auto-range.

        Returns:
            float: DC voltage in volts
        """
        if range_value is None:
            result = self.query("MEAS:VOLT:DC? AUTO")
        else:
            result = self.query(f"MEAS:VOLT:DC? {range_value}")
        return float(result.strip())

    # ==========================================================================
    # Advanced Measurement Methods
    # =========================================================================

    def measure_multiple(self, count: int) -> list[float]:
        """Take multiple measurements with optional delay between them.

        Args:
            count (int): Number of measurements to take

        Returns:
            list[float]: List of measurement values
        """
        self.set_number_of_samples(count)

        measurements = self.read()
        print(measurements)
        return measurements

    def measure_average(self, count: int) -> tuple[float, float]:
        """Take multiple measurements and return average and standard deviation.

        Args:
            count (int): Number of measurements to average

        Returns:
            tuple[float, float]: (average, standard_deviation)
        """
        measurements = self.measure_multiple(count)

        if not measurements:
            raise ValueError("No measurements taken")

        avg = sum(measurements) / len(measurements)
        if len(measurements) > 1:
            variance = sum((x - avg) ** 2 for x in measurements) / (
                len(measurements) - 1
            )
            std_dev = variance**0.5
        else:
            std_dev = 0.0

        return avg, std_dev

    # ==========================================================================
    # Query Methods
    # ==========================================================================

    def get_range(self) -> float:
        """Get the current measurement range."""
        result = self.query("SENS:VOLT:RANG?")
        return float(result.strip())

    def get_nplc(self) -> float:
        """Get the current NPLC setting."""
        result = self.query("SENS:VOLT:NPLC?")
        return float(result.strip())

    def get_resolution(self) -> float:
        """Get the current resolution setting."""
        result = self.query("SENS:VOLT:RES?")
        return float(result.strip())

    def get_configuration(self) -> str:
        """Get the current configuration of the DMM.

        Returns:
            str: Current configuration string
        """
        config = self.query("CONF?")
        logger.debug(f"Current configuration: {config.strip()}")
        return config.strip()


def main():
    from utils.const import KEYSIGHT_DMM_IP_HIGH as IP_HIGH
    
    """Command line interface for testing the DMM driver."""
    parser = argparse.ArgumentParser(description="Keysight 34461A DMM Controller")
    parser.add_argument(
        "address", nargs="?", default=IP_HIGH, help="DMM IP address or VISA resource name"
    )
    parser.add_argument(
        "--range",
        type=float,
        default=None,
        help="Measurement range (auto if not specified)",
    )
    parser.add_argument(
        "--count", type=int, default=1, help="Number of measurements to take"
    )
    parser.add_argument(
        "--average", action="store_true", help="Calculate average and std dev"
    )
    parser.add_argument(
        "--nplc",
        type=float,
        default=1,
        help="Integration time in power line cycles (0.001-100)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        with Keysight34461A(args.address) as dmm:
            print(f"Connected to DMM: {dmm.idn().strip()}")
            print(f"Current configuration: {dmm.get_configuration()}")
            # Configure measurement
            dmm.configure(mode=MeasurementMode.VOLT_DC, range_value=args.range)
            print(f"Current configuration: {dmm.get_configuration()}")
            dmm.set_nplc(args.nplc)

            # Take measurements
            if args.average and args.count > 1:
                avg, std = dmm.measure_average(args.count)
                print(f"Average: {avg:.6f}")
                print(f"Std Dev: {std:.6f}")
            elif args.count > 1:
                measurements = dmm.measure_multiple(args.count)
                for i, value in enumerate(measurements):
                    print(f"Measurement {i + 1}: {value:.6f}")
            else:
                dmm.set_number_of_samples(1)
                value = dmm.get_measurement()[0]
                print(f"Measurement: {value:.6f}")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
