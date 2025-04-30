from chips.lm75 import LM75
from adafruit_pca9685 import PWMChannel


class SensorChannel:
    """Represents a single temperature sensor channel."""

    def __init__(self, temperature_sensor: LM75):
        self.temperature_sensor = temperature_sensor

    # === LM75 properties ===
    @property
    def temperature(self) -> float:
        """Get the current temperature reading from the sensor"""
        return self.temperature_sensor.temperature

    def get_hysteresis(self) -> float:
        """Get the hysteresis temperature setting"""
        self._hysteresis_cached = self.temperature_sensor.temperature_hysteresis
        return self._hysteresis_cached

    @property
    def hysteresis(self) -> float:
        """Get the hysteresis temperature setting"""
        if not hasattr(self, "_hysteresis_cached"):
            print("Hysteresis not cached, getting from sensor")
            self.get_hysteresis()
        return self._hysteresis_cached

    @hysteresis.setter
    def hysteresis(self, value: float) -> None:
        """Set the hysteresis temperature"""
        self._hysteresis_cached = value
        self.temperature_sensor.temperature_hysteresis = value

    def get_ot_shutdown(self) -> float:
        """Get the over-temperature shutdown setting"""
        self._ot_shutdown_cached = self.temperature_sensor.temperature_shutdown
        return self._ot_shutdown_cached

    @property
    def ot_shutdown(self) -> float:
        """Get the over-temperature shutdown setting"""
        if not hasattr(self, "_ot_shutdown_cached"):
            print("OT shutdown not cached, getting from sensor")
            self.get_ot_shutdown()
        return self._ot_shutdown_cached

    @ot_shutdown.setter
    def ot_shutdown(self, value: float) -> None:
        """Set the over-temperature shutdown threshold"""
        self._ot_shutdown_cached = value
        self.temperature_sensor.temperature_shutdown = value

    @property
    def load_power(self) -> float:
        return None

    @load_power.setter
    def load_power(self, power: float) -> None:
        """Set the load power in Watts"""
        pass

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
            "load_power": self.load_power,  # Placeholder for load power
        }


class Channel(SensorChannel):
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

    # === PCA9685 properties ===
    @property
    def frequency(self) -> float:
        """Get the PWM frequency"""
        return self.pwm_channel.frequency

    def get_load_power(self) -> float:
        """Get the current load power in Watts"""
        self._load_power_cached = (
            self.pwm_channel.duty_cycle / 0xFFFF * self.max_power
        )  # FIXME: check if this is correct

    @property
    def load_power(self) -> float:
        """Get the current load power in Watts"""
        if not hasattr(self, "_load_power_cached"):
            print("Load power not cached, getting from PWM channel")
            self.get_load_power()
        return self._load_power_cached

    @load_power.setter
    def load_power(self, power: float) -> None:
        """Set the load power in Watts"""
        if power > self.max_power:
            # raise ValueError(f"Power must be less than {self.max_power} W")
            power = self.max_power
            print(
                f"Power set to maximum value of {self.max_power} W. "
                f"Requested power was {power} W."
            )

        duty_cycle = int(power / self.max_power * 0xFFFF)
        self._load_power_cached = duty_cycle / 0xFFFF * self.max_power

        self.pwm_channel.duty_cycle = duty_cycle
