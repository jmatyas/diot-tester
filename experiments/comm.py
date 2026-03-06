from artiq.experiment import *
from artiq.coredevice.i2c import i2c_read_many, i2c_write_many, I2CError
from artiq.coredevice.kasli_i2c import port_mapping


@kernel
def switch_select(ob):
    ob.i2c_switch0.set(3)  # SHARED
    try:
        ob.core.break_realtime()
        # PCA9539 I/O expander
        i2c_write_many(0, 0xEC, 0x02, [0])
        i2c_write_many(0, 0xEC, 0x02, [1 << ob.port])
        delay(100 * ms)
    except I2CError:
        ob.core.break_realtime()
        # MCP23017 I/O expander
        # Make sure no peripheral is selected
        i2c_write_many(0, 0x44, 0x02, [0])
        # Select given peripheral
        i2c_write_many(0, 0x44, 0x09, [1 << ob.port])
        delay(100 * ms)


@kernel
def switch_deselect(ob):
    ob.i2c_switch0.set(3)
    try:
        i2c_write_many(0, 0xEC, 0x02, [0])
    except I2CError:
        i2c_write_many(0, 0x44, 0x02, [0])
    ob.i2c_switch0.unset()


class TestI2CComm(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("i2c_switch0")

        self.port = port_mapping["DIOT2"]

        self.regs = [0] * 8

    @kernel
    def map_regs(self):
        switch_select(self)
        try:
            for addr in range(8):
                tmp = [0]
                i2c_read_many(0, 0xEC, addr, tmp)
                self.regs[addr] = tmp[0]
        finally:
            switch_deselect(self)

    def print_regs(self):
        fmt_str = ",".join([f"0x{v:02X}" for v in self.regs])
        print(f"[{fmt_str}]")

    @kernel
    def init_switch(self):
        self.i2c_switch0.set(3)  # SHARED
        i2c_write_many(0, 0xEC, 0x06, [0x00])  # all servmods as output
        i2c_write_many(0, 0xEC, 0x07, [0x00])  # OEn, DIR and Reset as output
        i2c_write_many(0, 0xEC, 0x03, [0x60])  # as above
        self.i2c_switch0.unset()

    def run(self):
        i = 2
        diot_slot = f"DIOT{i}"
        self.port = port_mapping[diot_slot]
        print(diot_slot)

        print("Before init regs:")
        self.map_regs()
        self.print_regs()
        self.init_switch()
        print("After init regs:")
        self.map_regs()
        self.print_regs()
        print("Setting EEM adapter LEDs to ON...")
        self.set_eem_adapter_leds()

    @kernel
    def set_eem_adapter_leds(self):
        dev_addr = 0x77
        switch_select(self)
        try:
            i2c_write_many(1, dev_addr << 1, 0x06, [0x1F])  # set LEDs to outputs
            i2c_write_many(1, dev_addr << 1, 0x02, [0x1F])
        finally:
            switch_deselect(self)
