# -*- coding: utf-8 -*-

__author__ = 'Awais khan'
__all__ = ('SI7021')

from senlib import logger
import time
from senlib.core.i2c import Sensor as I2CSensor


class SI7021(I2CSensor):
    """
    This is a driver implementation for the SILICON LABS SI7021 
    humidity / temperature sensor for use with Raspberry Pi computers.
    """

    DRIVER_NAME = 'si7021'

    ADDR = 0x40
    DEFAULT_ADDR = ADDR

    CMD_MEASURE_HUM = 0xF5
    CMD_MEASURE_TEMP = 0xF3
    CMD_LAST_TEMP = 0xE0

    def __init__(self, bus, addr=ADDR):
        super(SI7021, self).__init__(bus, addr)
        logger.debug('create SI7021(addr=%s) object', addr)
        self._temperature = self._humidity = 0.0

    @classmethod
    def driver_name(cls):
        return cls.DRIVER_NAME

    @classmethod
    def default_addr(cls):
        return cls.DEFAULT_ADDR

    def read_temperature(self):
        logger.debug('read temperature data')
        self._bus.write_byte(self.addr, self.CMD_MEASURE_TEMP)
        time.sleep(0.05)
        msb = self._bus.read_byte(self.addr)
        lsb = self._bus.read_byte(self.addr)
        data = (msb << 8) | lsb
        temp = (175.72 * data)/65536.0 - 46.85
        return temp

    def read_humidity(self):
        logger.debug('read humidity data')
        self._bus.write_byte(self.addr, self.CMD_MEASURE_HUM)
        time.sleep(0.05)
        msb = self._bus.read_byte(self.addr)
        lsb = self._bus.read_byte(self.addr)
        data = (msb << 8) | lsb
        hum = (125 * data)/65536.0 - 6
        return hum

    def measure(self):
        self._humidity = self.read_humidity()
        time.sleep(0.01)
        self._temperature = self.read_temperature()

        return {
            'temperature': self._temperature,
            'humidity': self._humidity
        }

    def temperature(self):
        return self._temperature

    def humidity(self):
        return self._humidity
