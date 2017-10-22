# -*- coding: utf-8 -*-

__author__ = 'Alexander Rüedlinger'
__all__ = ('BME280')

import struct
from senlib.core.i2c import Sensor as I2CSensor


class BME280(I2CSensor):
    """
    This is a quick and dirty driver implementation for the Bosch BME280 integrated environmental sensor
    for use with Raspberry Pi computers.

    Remarks and credits:
        * The compensation functions for computing the temperature, pressure, and humidity values
          are based on the Adafruit Python BME280 driver: https://github.com/adafruit/Adafruit_Python_BME280

        * The code for reading the BME280 sensor's calibration data is inspired by the implementation
        for ESP8266 boards: https://github.com/catdog2/mpy_bme280_esp8266
    """

    DRIVER_NAME = 'bme280'

    ADDR = 0x77
    DEFAULT_ADDR = ADDR

    REG_TEMP = 0xFA
    REG_PRESS = 0xF7
    REG_HUM = 0xFD

    REG_CONFIG = 0xF5
    REG_CTRL_MEAS = 0xF4
    REG_CTRL_HUM = 0xF2

    def __init__(self, i2c_ctrl, addr=DEFAULT_ADDR):
        super(BME280, self).__init__(i2c_ctrl, addr)

        self.dig_T1 = self.dig_T2 = self.dig_T3 = 0
        self.dig_P1 = self.dig_P2 = self.dig_P3 = self.dig_P4 = self.dig_P5 = self.dig_P6 = self.dig_P7 \
            = self.dig_P8 = self.dig_P9 = 0
        self.dig_H1 = self.dig_H2 = self.dig_H3 = self.dig_H4 = self.dig_H5 = self.dig_H6 = 0

        self.t_fine = 0.0
        self._temperature = self._humidity = self._pressure = 0.0

        self._read_calibration_data()

        self.osrs_h = 1
        self.osrs_t = 1
        self.osrs_p = 1
        self.power_mode = 3
        self.filter = 0
        self.t_sb = 5

        self._set_meas_and_hum()
        self._set_config()

    @classmethod
    def driver_name(cls):
        return cls.DRIVER_NAME

    @classmethod
    def default_addr(cls):
        return cls.DEFAULT_ADDR

    def _set_meas(self):
        settings = 0
        settings |= (self.osrs_t << 5)
        settings |= (self.osrs_p << 2)
        settings |= self.power_mode
        self._i2c_ctrl.write_byte_data(self.addr, self.REG_CTRL_MEAS, settings)

    def _set_hum(self):
        settings = 0
        settings |= self.osrs_h
        self._i2c_ctrl.write_byte_data(self.addr, self.REG_CTRL_HUM, settings)

    def _set_meas_and_hum(self):
        self._set_hum()
        self._set_meas()

    def _set_config(self):
        config = 0
        config |= (self.t_sb << 5)
        config |= (self.filter << 2)
        self._i2c_ctrl.write_byte_data(self.addr, self.REG_CONFIG, config)

    def _read_calibration_data(self):
        dig_88_A1 = self._i2c_ctrl.read_i2c_block_data(self.addr, 0x88, 26)
        dig_88_A1 = struct.unpack('<HhhHhhhhhhhhBB', bytearray(dig_88_A1))
        self.dig_T1, self.dig_T2, self.dig_T3, self.dig_P1, self.dig_P2, self.dig_P3, self.dig_P4, self.dig_P5, \
        self.dig_P6, self.dig_P7, self.dig_P8, self.dig_P9, _, self.dig_H1 = dig_88_A1

        dig_e1_e7 = self._i2c_ctrl.read_i2c_block_data(self.addr, 0xE1, 7)
        self.dig_H2, self.dig_H3 = struct.unpack('<hB', bytearray(dig_e1_e7[:3]))
        e4_sign = struct.unpack('<b', bytes([dig_e1_e7[3]]))[0]
        self.dig_H4 = (e4_sign << 4) | (dig_e1_e7[4] & 0xF)
        e6_sign = struct.unpack('<b', bytes([dig_e1_e7[5]]))[0]
        self.dig_H5 = (e6_sign << 4) | (dig_e1_e7[4] >> 4)
        self.dig_H6 = struct.unpack('<b', bytes([dig_e1_e7[6]]))[0]

    def _read_raw_sensor_data(self):
        press_msb, press_lsb, press_xlsb = self._i2c_ctrl.read_i2c_block_data(self.addr, self.REG_PRESS, 3)
        temp_msb, temp_lsb, temp_xlsb = self._i2c_ctrl.read_i2c_block_data(self.addr, self.REG_TEMP, 3)
        hum_msb, hum_lsb = self._i2c_ctrl.read_i2c_block_data(self.addr, self.REG_HUM, 2)

        adc_p = (press_msb << 12) | (press_lsb << 4) | (press_xlsb >> 4)
        adc_t = (temp_msb << 12) | (temp_lsb << 4) | (temp_xlsb >> 4)
        adc_h = (hum_msb << 8) | hum_lsb

        return adc_p, adc_t, adc_h

    def _compensate_temperature(self, adc_t):
        UT = float(adc_t)
        var1 = (UT / 16384.0 - self.dig_T1 / 1024.0) * float(self.dig_T2)
        var2 = ((UT / 131072.0 - self.dig_T1 / 8192.0) * (
        UT / 131072.0 - self.dig_T1 / 8192.0)) * float(self.dig_T3)
        self.t_fine = int(var1 + var2)
        temp = (var1 + var2) / 5120.0
        return temp

    def _compensate_pressure(self, adc_p):
        var1 = self.t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * self.dig_P6 / 32768.0
        var2 = var2 + var1 * self.dig_P5 * 2.0
        var2 = var2 / 4.0 + self.dig_P4 * 65536.0
        var1 = (
               self.dig_P3 * var1 * var1 / 524288.0 + self.dig_P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * self.dig_P1
        if var1 == 0:
            return 0
        p = 1048576.0 - adc_p
        p = ((p - var2 / 4096.0) * 6250.0) / var1
        var1 = self.dig_P9 * p * p / 2147483648.0
        var2 = p * self.dig_P8 / 32768.0
        p = p + (var1 + var2 + self.dig_P7) / 16.0
        return p

    def _compensate_humidity(self, adc_h):
        h = self.t_fine - 76800.0
        h = (adc_h - (self.dig_H4 * 64.0 + self.dig_H5 / 16384.0 * h)) * (
        self.dig_H2 / 65536.0 * (1.0 + self.dig_H6 / 67108864.0 * h * (
        1.0 + self.dig_H3 / 67108864.0 * h)))
        h = h * (1.0 - self.dig_H1 * h / 524288.0)
        if h > 100:
            h = 100
        elif h < 0:
            h = 0
        return h

    def read_temperature(self):
        adc_p, adc_t, adc_h = self._read_raw_sensor_data()
        return self._compensate_temperature(adc_t)

    def read_pressure(self):
        adc_p, adc_t, adc_h = self._read_raw_sensor_data()
        self._compensate_temperature(adc_t)
        return self._compensate_pressure(adc_p)

    def read_humidity(self):
        adc_p, adc_t, adc_h = self._read_raw_sensor_data()
        self._compensate_temperature(adc_t)
        return self._compensate_humidity(adc_h)

    def measure(self):
        adc_p, adc_t, adc_h = self._read_raw_sensor_data()
        self._temperature = self._compensate_temperature(adc_t)
        self._pressure = self._compensate_pressure(adc_p)
        self._humidity = self._compensate_humidity(adc_h)

        return {
            'temperature': self._temperature,
            'humidity': self._humidity,
            'pressure': self._pressure
        }

    def temperature(self):
        return self._temperature

    def pressure(self):
        return self._pressure

    def humidity(self):
        return self._humidity
