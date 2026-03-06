from artiq.experiment import *
from numpy import int32


class FastinoSquare(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.fastinos = []
        for i in range(8):
            self.fastinos.append(self.get_device(f"fastino{i}"))

        # Fastino has frame duration of around 392 ns (refer to Fastino coredevice
        # and phy and gateware for details). So below is 15 us-ish - rounded to
        # a multiple of the frame duration - to get a clean square wave without
        # jitter from the frame edges.
        self.half_period = 15.680 * us

        self.high_voltages = [int32(0) for i in range(16)]
        self.low_voltages = [int32(0) for i in range(16)]
        self.fastinos[0].voltage_group_to_mu(
            [9.9 for i in range(32)], self.high_voltages
        )
        self.fastinos[0].voltage_group_to_mu(
            [-9.9 for i in range(32)], self.low_voltages
        )

    @kernel
    def run(self):
        self.core.reset()
        self.kernelled_run()

    @kernel
    def kernelled_run(self):
        self.core.break_realtime()
        while True:
            for fastino in self.fastinos:
                fastino.set_group_mu(0, self.high_voltages)
            delay(self.half_period)
            for fastino in self.fastinos:
                fastino.set_group_mu(0, self.low_voltages)
            delay(self.half_period)
