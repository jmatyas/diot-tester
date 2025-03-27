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
            max_power = 5 # 5 Watts
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
        return self.pwm_channel.duty_cycle / 0xFFFF * self.max_power # FIXME: check if this is correct
    
    @load_power.setter
    def load_power(self, power: float):
        if power > self.max_power:
            raise ValueError("Power exceeds maximum power of the channel")
        
        print("duty cycle:", int(power / self.max_power * 0xFFFF))
        self.pwm_channel.duty_cycle = int(power / self.max_power * 0xFFFF)

    def set_configuration(self, hysteresis: float = None, ot_shutdown: float = None, power: float = None):
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

    def __init__(self, url="ftdi://ftdi:232h:/1", frequency=100000):
        os.environ["BLINKA_FT232H"] = url
        self._i2c = _I2C(frequency=frequency)

        # 2 EEPROM to EEM0
        self.eeproms = [
            EEPROM24AA02E48(self, address=0x50),
            # EEPROM24AA025E48(self._i2c, address=0x50),  # FIXME: collision
        ]

        self.i2c_mux = PCA9544A(self, address=0x70) # FIXME
        self.i2c_buses = [
            self.i2c_mux[0],
            self.i2c_mux[1],
            self.i2c_mux[2],
            self.i2c_mux[3],
        ]

        # # Mux channels 0 and 1 swapped
        self.lm75s = [
            LM75(self.i2c_buses[1], device_address=0x48 + addr) for addr in range(8)
        ] + [
            LM75(self.i2c_buses[0], device_address=0x48 + addr) for addr in range(8)
        ]

        self.i_monitor = MCP3221(self.i2c_buses[2], device_address=0x4D, reference_voltage=3.3)
        self.v_monitor = MCP3221(self.i2c_buses[3], device_address=0x4D, reference_voltage=3.3)

        self.pwm_chips = [
            PCA9685(self.i2c_buses[2], address=0x40),
            PCA9685(self.i2c_buses[2], address=0x41),
        ]

        self.power_channels = [
            Channel(self.pwm_chips[0].channels[i], self.lm75s[i]) for i in range(16)
        ]


        self.diot_conn_lm75s = [
            LM75(self.i2c_buses[3], device_address=0x49),  # P6 connector
            LM75(self.i2c_buses[3], device_address=0x4A),  # P1 connector
        ]
        self.middle_lm75 = LM75(self.i2c_buses[3], device_address=0x48)  # LM75 without load?
        self.pwm_chips[1].frequency = 1000
        self.middle_power = self.pwm_chips[1].channels[0]

    @property
    def current(self):
        # there is 16 resistive heaters, each around 5W from 12V -> each draws
        # around 0.4A; additionally there is one heater for 3.3V, that draws up
        # to 3A (around 10W) - indirectly from 12V as well.
        # 
        # FIXME: check if this is correct because it's against the specs
        # 0.4A * 16 + 3A = 6.4A + 3A = 9.4A
        # 
        #   - issue says that the LED bar-graph should show 12V rail load up to
        #       60W, which is 5A from 12V
        #   - calculations around INA195 were made with the assumption of total
        #       current of 6A.
        # 
        # In such case, the INA's output range would be up to around 3V 
        # (due to R_sense=0.005 Ohm and 100 V/V gain which results in 0.5 V/A),
        # but in case of 10A it would be up to 5V, which is unreachable for the
        # INA monitor since it's powered from 3.3V... (moreover, the MCP3221 ADC
        # is powered from 3.3V as well).
        # 
        # Let's assume that the current is around 6A, so the INA's output would
        # be around 3V.
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


if __name__ == "__main__":
    diot_tester = DIOTTester()
    eui48 = diot_tester.eeproms[0].eui64
    print("DIOT Tester EUI-48: 0x", "-".join([f"{x:02x}" for x in eui48]))

    # diot_tester.print_i2c_tree()

    # print("=== MISC LM75s")
    # for lm in [*diot_tester.diot_conn_lm75s, diot_tester.middle_lm75]:
    #     print(lm.temperature)
    #     print(lm.temperature_hysteresis)
    #     print()


    print("=== Measurements with no load:")
    print("\tcurrent:", diot_tester.current)
    print("\tvoltage:", diot_tester.voltage)
    print()

    pwr = diot_tester.middle_power
    print(pwr.duty_cycle)

    # # power_channels = diot_tester.power_channels
    # pwr_ch = diot_tester.power_channels[0]
    # print("=== Channel 0:")
    # # for i in range(5):
    # pwr_ch.load_power = 1
    # #     time.sleep(1)
        
    # print(pwr_ch.report())

    # # for ix, ch in enumerate(power_channels):
    # #     ch.load_power=2 # setting power results in 5.019607843137255; seems independent of the value set
    # #     print(f"Channel {ix}:")
    # #     print(ch.report())
