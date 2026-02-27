from artiq.experiment import *

class FastinoSquare(EnvExperiment):

    def build(self):
        self.setattr_device('core')

        self.fastinos = []
        for i in range(8):
            self.fastinos.append(self.get_device(f'fastino{i}'))

    @kernel
    def init_fastino(self):
        self.core.break_realtime()
        for fastino in self.fastinos:
            fastino.init()
            delay(200*us)


    def run(self):
        self.core.reset()
        self.init_fastino()
        self.kernelled_run()

    @kernel
    def kernelled_run(self):
        self.core.break_realtime()
        while True:
            for fastino in self.fastinos:
                fastino.set_group(0, [9.9 for i in range(32)])
                delay(15 * ms)
                fastino.set_group(0, [-9.9 for i in range(32)])
                delay(15 * ms)
        

