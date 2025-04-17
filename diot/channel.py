from chips.lm75 import LM75
from adafruit_pca9685 import PWMChannel


class Channel:
    """Represents a single load channel with temperature monitoring and power control."""

    def __init__(
        self,
        pwm_channel: PWMChannel,
        temperature_sensor: LM75,
        max_power: float | None = None,
    ):
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
        self,
        hysteresis: float | None = None,
        ot_shutdown: float | None = None,
        power: float | None = None,
    ) -> None:
        """Configure multiple parameters at once"""
        if hysteresis is not None:
            self.hysteresis = hysteresis
        if ot_shutdown is not None:
            self.ot_shutdown = ot_shutdown
        if power is not None:
            self.load_power = power

    def report(self) -> dict[str, float]:
        """Get a report of all channel parameters"""
        return {
            "temperature": self.temperature,
            "hysteresis": self.hysteresis,
            "ot_shutdown": self.ot_shutdown,
            "load_power": self.load_power,
        }
