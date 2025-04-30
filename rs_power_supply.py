"""
Rohde & Schwarz Power Supply Controller

This module provides a class for controlling Rohde & Schwarz power supply units
via VISA (SCPI commands).

For NGL202 with:
- Two independent channels
- Supports voltage, current measurement and setting
- Supports output on/off control
"""

import time
import pyvisa

MAX_V = 20
MIN_V = 0
MAX_I = 6  # if voltage is in range 0-6V, otherwise 3
MIN_I = 0.010


class RSPowerSupply:
    """
    Class to control Rohde & Schwarz power supply units.

    Primarily tested with NGL202 model but should work with other
    similar R&S power supplies that support standard SCPI commands.
    """

    def __init__(self, address, timeout_s=5):
        """
        Initialize the power supply connection.

        Args:
            resource_name (str): VISA resource name
                e.g., 'TCPIP::10.42.0.245::INSTR' for network connection
            timeout (int): Connection timeout in milliseconds
        """
        self.address = address
        self.timeout = timeout_s * 1000
        self.instrument = None
        self.connect()

    def connect(self):
        """Establish connection to the power supply."""
        rm = pyvisa.ResourceManager()
        try:
            self.instrument = rm.open_resource(
                f"TCPIP::{self.address}::INSTR",
            )
            self.instrument.timeout = self.timeout
            idn = self.idn()
            print(f"Connected to: {idn}")

            # Check if it's an R&S power supply
            if "Rohde&Schwarz" not in idn:
                print(
                    "Warning: Connected device may not be a Rohde & Schwarz power supply"
                )
        except Exception as e:
            print(f"Connection failed: {e}")
            raise e

    def disconnect(self):
        """Close the connection to the power supply."""
        if self.instrument:
            self.instrument.close()
            self.instrument = None
            print("Connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic connection closing."""
        self.disconnect()

    def cmd(self, cmd):
        self.instrument.write(cmd)

    def query(self, command):
        return self.instrument.query(command)

    def idn(self):
        """Get the identification string of the power supply."""
        return self.query("*IDN?")

    def reset(self):
        """Reset the power supply to default settings."""
        self.cmd("*RST")

    def clear_status(self):
        self.cmd("*CLS")

    def query_opc(self):
        return self.query("*OPC?")

    def wait_for_opc(self, timeout=5):
        t = time.monotonic()
        while int(self.query_opc()) != 1:
            if time.monotonic() - t > timeout:
                raise TimeoutError("Operation timed out")

    # ==========================================================================
    def select_channel(self, channel=1):
        """Select the channel for subsequent commands."""
        if channel not in [1, 2]:
            raise ValueError("Channel must be 1 or 2")
        self.cmd(f"INST:NSEL {channel}")

    def query_channel(self):
        """Query the currently selected channel."""
        return int(self.query("INST:NSEL?"))

    # Channel-specific methods
    def set_voltage(self, voltage):
        """Set the voltage"""
        if voltage > MAX_V or voltage < MIN_V:
            raise ValueError(f"Voltage must be between {MIN_V} and {MAX_V} V")
        self.cmd(f"SOUR:VOLT {voltage}")

    def get_voltage(self):
        """Query the voltage."""
        return float(self.query("SOUR:VOLT?"))

    def measure_voltage(self):
        cmd = "MEAS:VOLT?"
        return float(self.query(cmd))

    def set_current(self, current):
        """Set the current limit"""
        if current > MAX_I or current < MIN_I:
            raise ValueError(f"Current must be between {MIN_I} and {MAX_I} A")
        self.cmd(f"SOUR:CURR {current}")

    def get_current(self, channel=1):
        """Get the set current."""
        return float(self.query("SOUR:CURR?"))

    def measure_current(self):
        cmd = "MEAS:CURR?"
        return float(self.query(cmd))

    def measure(self):
        """Measure voltage and current."""
        voltage = self.measure_voltage()
        current = self.measure_current()
        return voltage, current

    def set_channel(self, voltage, current, channel=1):
        """Set voltage and current for a specific channel."""
        if channel not in [1, 2]:
            raise ValueError("Channel must be 1 or 2")
        if voltage > MAX_V or voltage < MIN_V:
            raise ValueError(f"Voltage must be between {MIN_V} and {MAX_V} V")
        if current > MAX_I or current < MIN_I:
            raise ValueError(f"Current must be between {MIN_I} and {MAX_I} A")
        self.cmd(f"APPL {voltage},{current},OUT{channel}")

    # ===================================================================
    def set_output_state(self, enable=True):
        """Turn on the output."""
        state = "1" if enable else "0"
        self.cmd(f"OUTP:SEL {state}")
        self.cmd(f"OUTP {state}")

    def get_output_state(self):
        """Get the output state for a specific channel."""
        response = self.query("OUTP?")
        print(f"OUTP? response: {int(response)}")
        return int(response) == 1 or response.lower() == "on"

    def set_ovp(self, voltage_lvl, enable=True):
        """Set overvoltage protection threshold."""
        self.set_ovp_state(enable)
        self.cmd(f"VOLT:PROT:LEV {voltage_lvl}")

    def get_ovp(self, channel=1):
        """Get overvoltage protection threshold."""
        state = int(self.query("VOLT:PROT?"))
        lvl = float(self.query("VOLT:PROT:LEV?"))
        return state, lvl

    def set_ovp_state(self, enable=True):
        """Enable overvoltage protection."""
        state = "ON" if enable else "OFF"
        self.cmd(f"VOLT:PROT {state}")


# Example usage
if __name__ == "__main__":
    # Example usage of the class
    psu = RSPowerSupply("10.42.0.245")

    try:
        print(f"IDN: {psu.idn()}")
        psu.reset()
        psu.clear_status()
        psu.select_channel(1)
        print(f"Selected channel: {psu.query_channel()}")
        print(f"Current voltage: {psu.get_voltage()}")
        print(f"Current current: {psu.get_current()}")
        print(f"Output state: {psu.get_output_state()}")
        psu.set_voltage(12.0)
        psu.set_current(2.0)
        psu.set_output_state(True)
        print(f"Set voltage: {psu.get_voltage()}")
        print(f"Set current: {psu.get_current()}")
        print(f"Output state: {psu.get_output_state()}")
        time.sleep(2)
        print(f"Measured voltage: {psu.measure_voltage()}")
        print(f"Measured current: {psu.measure_current()}")
        print(f"Measured values: {psu.measure()}")

        # psu.set_output_state(False)
        # print(f"Output state: {psu.get_output_state()}")
        # print(f"Measured voltage: {psu.measure_voltage()}")
        # print(f"Measured current: {psu.measure_current()}")
        # print(f"Measured values: {psu.measure()}")

    finally:
        psu.disconnect()
