# -*- coding: utf-8 -*-

__author__ = 'Awais khan'
__all__ = ('Sensor')


class Sensor(object):
    
    DRIVER_NAME = 'mock-sensor'

    def measure(self):
        return {
            'temperature': 28.5,
            'humidity': 25.2
        }
