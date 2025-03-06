# TO CHECK

import board
import busio

class PCA9544:
    def __init__(self, i2c, address=0x70):
        self.i2c = i2c
        self.address = address

    def select_channel(self, channel):
        if channel < 0 or channel > 3:
            raise ValueError("Invalid channel")

        self.i2c.writeto(self.address, bytes([1 << channel]))

    def disable_all_channels(self):
        self.i2c.writeto(self.address, bytes([0]))

# Example usage
i2c = busio.I2C(board.SCL, board.SDA)
mux = PCA9544(i2c)

# Select channel 0
mux.select_channel(0)

# Disable all channels
mux.disable_all_channels()