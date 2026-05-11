from artiq.experiment import *


class FastinoSquare(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.fastinos = []
        device_db = self.get_device_db()
        fastino_keys = sorted(key for key in device_db if key.startswith("fastino"))
        for key in fastino_keys:
            self.fastinos.append(self.get_device(key))
    
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
