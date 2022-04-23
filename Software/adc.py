# Loosely based on the ABElectronics ADC Pi 8-Channel ADC module
import math
from enum import IntEnum, auto
from typing import Literal
import time

from smbus2 import SMBus


class ConversionMode(IntEnum):
    ONE_SHOT = 0x00
    CONTINUOUS = 0x10


BitRate = Literal[12, 14, 16, 18]
Gain = Literal[1, 2, 4, 8]
Channel = Literal[1, 2, 3, 4, 5, 6, 7, 8]


def updatebyte(byte, mask, value):
    byte &= mask
    byte |= value
    return byte


class ADC:
    __adc1_address = 0x68
    __adc2_address = 0x69

    __config_register: int = 0x9C

    __bitrate: BitRate = 18
    __conversionmode: ConversionMode = ConversionMode.ONE_SHOT
    __gain: Gain = 1

    def __init__(self, address=0x68, address2=0x69, rate=18):
        self.__bus = SMBus(1)
        if address >= 0x68 and address <= 0x6F:
            self.__adc1_address = address
        else:
            raise ValueError("address out of range 0x68 to 0x6F")

        if address2 >= 0x68 and address2 <= 0x6F:
            self.__adc2_address = address2
        else:
            raise ValueError("address2 out of range 0x68 to 0x6F")
        self.bitrate = rate

    @property
    def bitrate(self):
        return self.__bitrate

    @bitrate.setter
    def bitrate(self, rate: BitRate):
        self.__bitrate = rate

        config_value = {12: 0x00, 14: 0x04, 16: 0x08, 18: 0x0C}[rate]
        self.__config_register = updatebyte(self.__config_register, 0xF3, config_value)

        self.__bus.write_byte(self.__adc1_address, self.__config_register)
        self.__bus.write_byte(self.__adc2_address, self.__config_register)

    @property
    def gain(self):
        return self.__gain

    @gain.setter
    def gain(self, gain):
        self.__gain = gain

        config_value = {1: 0x00, 2: 0x01, 4: 0x02, 8: 0x03}[gain]
        self.__config_register = updatebyte(self.__config_register, 0xFC, config_value)

        self.__bus.write_byte(self.__adc1_address, self.__config_register)
        self.__bus.write_byte(self.__adc2_address, self.__config_register)

    @property
    def conversion_mode(self) -> ConversionMode:
        return self.__conversionmode

    @conversion_mode.setter
    def conversion_mode(self, mode: ConversionMode):
        self.__conversionmode = mode
        self.__config_register = updatebyte(self.__config_register, 0xEF, mode)

    def read_raw(self, channel: Channel):

        # select the channel to read from
        channel_on_chip = (channel - 1) % 4
        channel_address = 0x20 * channel_on_chip

        config = self.__config_register

        config = updatebyte(config, 0x9F, channel_address)

        # select the i2c address of the chip for the channel
        address = self.__adc1_address if channel <= 4 else self.__adc2_address

        if self.__conversionmode == ConversionMode.ONE_SHOT:
            # start the conversion
            self.__bus.write_byte(address, config | (1 << 7))

        # determine a reasonable amount of time to wait for a conversion
        if self.__bitrate == 18:
            seconds_per_sample = 0.26666
        elif self.__bitrate == 16:
            seconds_per_sample = 0.06666
        elif self.__bitrate == 14:
            seconds_per_sample = 0.01666
        elif self.__bitrate == 12:
            seconds_per_sample = 0.00416
        timeout_time = time.time() + (100 * seconds_per_sample)

        # keep reading the adc data until the conversion result is ready
        adc_reading = [0, 0, 0]
        num_bytes = math.ceil(self.__bitrate / 8)
        while True:
            *adc_reading, cmd_byte = self.__bus.read_i2c_block_data(
                address, config, num_bytes + 1
            )
            # check if bit 7 of the command byte is 0.
            if (cmd_byte & (1 << 7)) == 0:
                break
            elif time.time() > timeout_time:
                raise TimeoutError(f"read_raw: channel {channel} conversion timed out")
            else:
                # yield execution for a bit
                time.sleep(0.00001)

        # convert the 2-s complement binary value to a python integer
        sign_bit_position = self.__bitrate - 1
        value = 0
        for byte in range(num_bytes):
            if byte == 0 and (self.__bitrate % 8) != 0:
                # mask the unused bits in the most significant byte
                adc_reading[byte] &= (2 ** (self.__bitrate % 8)) - 1

            value |= adc_reading[byte] << (8 * ((num_bytes - byte) - 1))

        sign_bit = bool(value & (1 << sign_bit_position))

        if sign_bit:
            # clear the sign bit and calculate the complement
            value = value & ~(1 << sign_bit_position)
            value = value - (2**sign_bit_position)

        return value
