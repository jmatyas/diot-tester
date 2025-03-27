# TO CHECK

import board
from busio import I2C
from typing_extensions import Literal
from circuitpython_typing import ReadableBuffer, WriteableBuffer
import time
from typing import List

from micropython import const


_DEFAULT_ADDRESS = const(0x70)

class PCA9544A_Channel:
    def __init__(self, pca: "PCA9544A", channel: int) -> None:
        self.pca = pca
        self.channel_code = bytearray([1 << 2 | channel])

    def _channel_op(func):
        def wrapper(self, *args, **kwargs):
            self.pca.i2c.writeto(self.pca.address, self.channel_code)
            ret = func(self, *args, **kwargs)
            self.pca.i2c.writeto(self.pca.address, b"\x00")
            return ret

        return wrapper

    def try_lock(self) -> bool:
        """Pass through for try_lock."""
        while not self.pca.i2c.try_lock():
            time.sleep(0)
        return True

    def unlock(self) -> bool:
        """Pass through for unlock."""
        return self.pca.i2c.unlock()

    @_channel_op
    def readfrom_into(self, address: int, buffer: ReadableBuffer, **kwargs):
        """Pass through for readfrom_into."""
        if address == self.pca.address:
            raise ValueError("Device address must be different than PCA9544A address.")
        return self.pca.i2c.readfrom_into(address, buffer, **kwargs)

    @_channel_op
    def writeto(self, address: int, buffer: WriteableBuffer, **kwargs):
        """Pass through for writeto."""
        if address == self.pca.address:
            raise ValueError("Device address must be different than PCA9544A address.")
        return self.pca.i2c.writeto(address, buffer, **kwargs)

    @_channel_op
    def writeto_then_readfrom(
        self,
        address: int,
        buffer_out: WriteableBuffer,
        buffer_in: ReadableBuffer,
        **kwargs
    ):
        """Pass through for writeto_then_readfrom."""
        # In linux, at least, this is a special kernel function call
        if address == self.pca.address:
            raise ValueError("Device address must be different than PCA9544A address.")
        return self.pca.i2c.writeto_then_readfrom(
            address, buffer_out, buffer_in, **kwargs
        )

    @_channel_op
    def scan(self, write: bool = False) -> List[int]:
        """Perform an I2C Device Scan"""
        return self.pca.i2c.scan(write)

    def poll(self, device_address: int) -> None:
        """implementation taken from i2c_device.I2CDevice.__poll_for_device()"""
        self.try_lock()

        try:
            self.writeto(device_address, b"")
        except OSError:
            # some OS's dont like writing an empty bytesting...
            # Retry by reading a byte
            try:
                result = bytearray(1)
                self.readfrom_into(device_address, result)
            except OSError:
                # pylint: disable=raise-missing-from
                raise ValueError("No I2C device at address: 0x%x" % device_address)
                # pylint: enable=raise-missing-from
        finally:
            self.i2c.unlock()

    
class PCA9544A:
    def __init__(self, i2c: I2C, address: int = _DEFAULT_ADDRESS) -> None:
        self.i2c = i2c
        self.address = address
        self.channels = [None] * 4

    def __len__(self) -> Literal[4]:
        return 4
    
    def __getitem__(self, key: int) -> "PCA9544A_Channel":
        if not 0 <= key <= 3:
            raise IndexError("Channel must be an integer in the range: 0-3.")
        if self.channels[key] is None:
            self.channels[key] = PCA9544A_Channel(self, key)
        return self.channels[key]
