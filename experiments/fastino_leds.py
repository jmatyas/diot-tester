from artiq.experiment import *

class FastinoLeds(EnvExperiment):

    def build(self):
        self.setattr_device('core')

        self.fastinos = []
        for i in range(8):
            self.fastinos.append(self.get_device(f'fastino{i}'))

        print(f"Found {len(self.fastinos)} Fastinos in `device_db.py`")

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
        for j in range(10):
            for i in range(8):
                led_marker = 1 << i
                for fastino in self.fastinos:
                    fastino.set_leds(led_marker)
                delay(200*ms)

        

