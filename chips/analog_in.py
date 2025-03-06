from chips.mcp3221 import MCP3221


class AnalogIn:
    """AnalogIn Mock Implementation for ADC Reads."""

    def __init__(self, mcp: MCP3221) -> None:
        """AnalogIn

        :param mcp: The MCP3221 object.
        """
        self._mcp = mcp

    @property
    def voltage(self) -> float:
        """Returns the value of an ADC in volts."""

        if not self._mcp:
            raise RuntimeError(
                "Underlying ADC does not exist, likely due to calling `deinit`"
            )
        raw_reading = self._mcp._read_data()
        return ((raw_reading & 0xFFF) / 4096) * self._mcp.reference_voltage

    @property
    def value(self) -> int:
        """Returns the value of an ADC."""

        if not self._mcp:
            raise RuntimeError(
                "Underlying ADC does not exist, likely due to calling `deinit`"
            )

        return self._mcp._read_data() & 0xFFF

    @property
    def reference_voltage(self) -> float:
        """The maximum voltage measurable (also known as the reference voltage) as a float in
        Volts. """
        if not self._mcp:
            raise RuntimeError(
                "Underlying ADC does not exist, likely due to calling `deinit`"
            )
        return self._mcp.reference_voltage

    def deinit(self) -> None:
        """Release the reference to the MCP3221. Create a new AnalogIn to use it again."""
        self._mcp = None