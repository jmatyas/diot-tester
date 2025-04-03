import os
import time

from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.i2c import I2C as _I2C
from adafruit_bus_device import i2c_device
from busio import I2C

from chips.eeprom_24aa025e48 import EEPROM24AA025E48, EEPROM24AA02E48
from chips.lm75 import LM75
from chips.pca9544 import PCA9544A
from adafruit_pca9685 import PCA9685
from chips.mcp3221 import MCP3221


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
    def __init__(self, pwm_channel, temperature_sensor, max_power=None):
        if max_power is None:
            max_power = 5  # 5 Watts
        self.pwm_channel = pwm_channel
        self.temperature_sensor = temperature_sensor
        self.max_power = max_power

    # === LM75 properties ===
    @property
    def temperature(self):
        return self.temperature_sensor.temperature

    @property
    def hysteresis(self):
        return self.temperature_sensor.temperature_hysteresis

    @hysteresis.setter
    def hysteresis(self, value: float):
        self.temperature_sensor.temperature_hysteresis = value

    @property
    def ot_shutdown(self):
        return self.temperature_sensor.temperature_shutdown

    @ot_shutdown.setter
    def ot_shutdown(self, value: float):
        self.temperature_sensor.temperature_shutdown = value

    # === PCA9685 properties ===
    @property
    def frequency(self):
        return self.pwm_channel.frequency

    @property
    def load_power(self):
        return (
            self.pwm_channel.duty_cycle / 0xFFFF * self.max_power
        )  # FIXME: check if this is correct

    @load_power.setter
    def load_power(self, power: float):
        if power > self.max_power:
            raise ValueError(f"Power must be less than {self.max_power} W")

        self.pwm_channel.duty_cycle = int(power / self.max_power * 0xFFFF)

    def set_configuration(
        self, hysteresis: float = None, ot_shutdown: float = None, power: float = None
    ):
        if hysteresis is not None:
            self.hysteresis = hysteresis
        if ot_shutdown is not None:
            self.ot_shutdown = ot_shutdown
        if power is not None:
            self.load_power = power

    def report(self):
        return {
            "temperature": self.temperature,
            "hysteresis": self.hysteresis,
            "ot_shutdown": self.ot_shutdown,
            "load_power": self.load_power,
        }


class DIOTTester(I2C):
    scan_blacklist = [0x70]

    def __init__(
        self, url="ftdi://ftdi:232h:/1", frequency=100000, ot_shutdown=80, hysteresis=75, serial=None
    ):
        if serial is not None:
            url = f"ftdi://::{serial}/1"
        os.environ["BLINKA_FT232H"] = url

        # this is workaround; it seems that without setting the frequency explicitly
        # the FTDI device is unable to communicate with devices on I2C bus every
        # second time the program is run (it's rather not a problem with the device,
        # but with the library or configuration). From the scope it seems that
        # FTDI produces START condition, but no data is sent afterwards (it doesn't
        # produce clock..., however, STOP condition is sent).
        self._i2c = _I2C(frequency=frequency)
        ftdi = self._i2c._i2c.ftdi
        ftdi.set_frequency(frequency)

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

        self.init(ot_shutdown, hysteresis)

    def init(self, ot_shutdown=80, hysteresis=75):
        # enable auto-increment so we can write/read registers using CP structures
        for pwm in self.pwm_chips:
            read_mode1 = pwm.mode1_reg
            pwm.mode1_reg = read_mode1 | 0x20

        for channel in self.load_channels:
            channel.set_configuration(ot_shutdown=ot_shutdown, hysteresis=hysteresis)

    @property
    def current(self):
        # IN195 senses current on 0.005 Ohm resistor and amplifies it by 100 V/V,
        # which results in 0.5 V/A of 'transimpedance'.
        voltage_reading = self.i_monitor.voltage
        return voltage_reading / 0.5

    @property
    def voltage(self):
        # there is a voltage divider of 1/4 on the board, so the voltage
        # reading is 4 times lower than the actual voltage
        voltage_reading = self.v_monitor.voltage
        return voltage_reading * 4

    def scan(self, write=False):
        # Override method from busio.i2c.scan, so it accepts one positional
        # argument
        return self._i2c.scan(write)

    def print_i2c_tree(self):
        # on each I2C bus there is EEPROM detected. it's due to the fact, that
        # the EEPROMs are connected BEFORE the I2C MUX so, they are always detected
        # (they just respond to polling on their address)
        for ix, bus in enumerate([self, *self.i2c_buses]):
            bus_name = "I2C Shared Bus" if ix == 0 else f"I2C Bus {ix}"
            detected = bus.scan(write=True)
            print(f"{bus_name}:")
            print(make_i2c_graph(detected))

    def set_pwm_frequency(self, chip_no, frequency):
        if frequency < 24 or frequency > 1526:
            raise ValueError("Frequency must be between 24 and 1526 Hz")
        self.pwm_chips[chip_no].frequency = frequency


if __name__ == "__main__":
    diot_serials = ["DT01"]
    diot_tester = DIOTTester(ot_shutdown=80, hysteresis=70, serial=diot_serials[0])
    eui48 = diot_tester.eeprom.eui64
    print("DIOT Tester EUI-48: 0x", "-".join([f"{x:02x}" for x in eui48]))

    def measure(diot_tester):
        i0 = diot_tester.current
        v0 = diot_tester.voltage

        print("=== Measurements with load:")
        print("\tcurrent [A]:", i0)
        print("\tvoltage [V]:", v0)
        print("\tpower [W]:", i0 * v0)
    
    # diot_tester.print_i2c_tree()

    # time.sleep(1)
    i0 = diot_tester.current
    v0 = diot_tester.voltage

    print("=== Measurements with no load:")
    print("\tcurrent [A]:", i0)
    print("\tvoltage [V]:", v0)

    # # for ix, channel in enumerate(diot_tester.load_channels[:-1]):
    # #     channel.load_power = 0

    # # print("=== Measurements with load:")
    # # print("\tcurrent:", diot_tester.current)
    # # print("\tvoltage:", diot_tester.voltage)

    # for i in range(10):
    #     for ix, channel in enumerate(diot_tester.load_channels):
    #         r = channel.report()
    #         if r["temperature"] > 55:
    #             print(f"OT: ch{ix}: {r['temperature']}°C... shutting down")
    #             channel.load_power = 0
    #         elif r["temperature"] > 35:
    #             print(f"Channel{ix}: {r['temperature']}°C")
    #         # channel.load_power = 5
    #     print()
    #     time.sleep(0.5)

    set_p = []
    ii = []
    vv = []
    pp = []
    diot_tester.set_pwm_frequency(1, 1500)

    for i in range(40, 55, 5):
        lpower = i / 10
        set_p.append(lpower)
        for ix, channel in enumerate(diot_tester.load_channels[:5]):
            channel.load_power = lpower
            print(channel.report())
        time.sleep(1)

    time.sleep(5)

    # for ix, channel in enumerate(diot_tester.load_channels[:-1]):
    #     channel.load_power = 2

    # for i in range(10):
    #     measure(diot_tester)
    #     for ix, channel in enumerate(diot_tester.load_channels[:-1]):
    #         r = channel.report()
    #         if r["temperature"] > 55:
    #             print(f"OT: ch{ix}: {r['temperature']}°C... shutting down")
    #             channel.load_power = 0
    #         elif r["temperature"] > 35:
    #             print(f"Channel{ix}: {r['temperature']}°C")
    #     time.sleep(0.5)

    # for i in range(0, 35, 5):
    #     lpower = i / 10
    #     set_p.append(lpower)
    #     diot_tester.load_channels[-1].load_power = lpower
    #     time.sleep(1)

    #     i1 = diot_tester.current
    #     v1 = diot_tester.voltage
    #     ii.append(i1)
    #     vv.append(v1)
    #     pp.append(i1 * 3.3)
    #     print("=== Measurements with load:")
    #     print("\tset power [W]:", lpower)
    #     print("\tcurrent [A]:", i1)
    #     print("\tvoltage [V]:", v1)
    #     print("\tpower [W]:", i1 * 3.3)

    # diot_tester.load_channels[-1].load_power = 0

    # with open("results.txt", "w") as f:
    #     f.write("set_power,current,voltage,power\n")
    #     for i in range(len(set_p)):
    #         f.write(f"{set_p[i]},{ii[i]},{vv[i]},{pp[i]}\n")

    diot_tester.load_channels[-1].load_power = 0
    # for i in range(10):
    #     i0 = diot_tester.current
    #     v0 = diot_tester.voltage

    #     print("=== Measurements with no load:")
    #     print("\tcurrent [A]:", i0)
    #     print("\tvoltage [V]:", v0)
    #     print("\tpower [W]:", i0 * 3.3)

    for ix, channel in enumerate(diot_tester.load_channels[:-1]):
        channel.load_power = 0