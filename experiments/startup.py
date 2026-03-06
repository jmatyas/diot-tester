from artiq.experiment import *


class FastinoSquare(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.fastinos = []
        for i in range(8):
            self.fastinos.append(self.get_device(f"fastino{i}"))

    @kernel
    def init_fastino(self):
        for fastino in self.fastinos:
            fastino.init()
            delay(200 * us)

    @kernel
    def run(self):
        self.core.reset()
        self.core.break_realtime()
        self.init_fastino()
