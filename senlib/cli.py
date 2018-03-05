# -*- coding:utf-8 -*-

__author__ = 'Alexander Rüedlinger'

from collections import OrderedDict
import argparse
from .__version__ import __version__
import json
from xml.dom.minidom import parseString
from dicttoxml import dicttoxml
from datetime import datetime
from senlib import logger
from senlib.i2c import DriverNotFound
from senlib.i2c import get_sensor_driver
from senlib.core.i2c import SMBus
import asyncio
import sys
import logging


class Application:
   
    DESCRIPTION = ''

    def __init__(self, loop=None, client=None):
        self._loop = loop or asyncio.get_event_loop()
        self._parser = argparse.ArgumentParser(description=self.DESCRIPTION)
        self._add_base_arguments()
        self._add_extra_arguments()
        self._args = self._parse_args()

        try:
            self._args.poll
        except AttributeError:
            self._args.poll = -1
        
        self._sensor = None

        if self._args.debug:
            logging.basicConfig(level=logging.DEBUG)
    
        self._i2caddr = int(self._args.addr, 0) if self._args.addr else None

        if self._args.debug:
            logging.basicConfig(level=logging.DEBUG)

        self._loop = asyncio.get_event_loop()
        if self._args.mock:
            from senlib.mock import Sensor
            self._sensor = Sensor()
        else:
            try:
                i2c_ctrl = SMBus(bus=self._args.bus)
                driver_class = get_sensor_driver(name=self._args.sensor)
                self._sensor = driver_class(i2c_ctrl, self._i2caddr or driver_class.default_addr())

            except DriverNotFound as e:
                print(e)
                sys.exit(1)

    def _add_base_arguments(self):
        self._parser.add_argument('--version', action='version', version='%(prog)s {}'
                .format(__version__), help='Print version number.')
        
        self._parser.add_argument('sensor', help='Set I2C sensor driver.')
        self._parser.add_argument('--mock', dest='mock', help='Use a mock sensor.', 
                action='store_true')

        self._parser.add_argument('-a', '--address', type=str, dest='addr', 
            help='Set I2C address.')
        self._parser.add_argument('-b', '--bus', type=int, dest='bus', help='Set I2C bus.', 
                default=1)
        self._parser.add_argument('-d', '--debug', dest='debug', help='Start debug mode.',
                action='store_true')
      
    def _add_extra_arguments(self):
        pass

    def _parse_args(self):
        return self._parser.parse_args()

    def _handle_data(self, data):
        pass

    def _start(self):
        def callback(num):
            sensor_data = self._sensor.measure()
            self._handle_data(sensor_data)
            if num != self._args.poll:
                self._loop.call_later(self._args.interval, callback, num+1)
            else:
                self._loop.stop()
                    
        self._loop.call_soon(callback, 1)

    def _before_start(self):
        pass

    def _after_stop(self):
        pass

    def run(self):
        self._before_start()
        self._start()
        try:
           self._loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._after_stop()


class SenlibCLI(Application):
   
    DESCRIPTION = 'senlib - Basic CLI for retrieving data for some I2C sensors.'

    def __init__(self, loop=None, client=None):
        super().__init__(loop, client)

    def _add_extra_arguments(self):
        self._parser.add_argument('-p', '--poll', type=int, dest='poll', nargs='?', 
                action='store', help='Start polling loop.', default=1)
        self._parser.add_argument('-i', '--interval', type=float, dest='interval', 
                help='Set sampling interval.', default=2)

        self._parser.add_argument('-f', '--format', type=str, dest='format', 
                help='Set output format.', choices=['json', 'xml', 'txt'], 
                default='txt')
        self._parser.add_argument('--pretty-print', dest='pretty_print', 
            help='Use pretty print output format.', action='store_true')
        self._parser.add_argument('-o', '--output', type=str, dest='output', 
                help='Save output to a file.')

    def _handle_data(self, data):
        self._generate_output(self._args, self._sensor, data)

    def _generate_output(self, args, sensor, sensor_data):
        data = OrderedDict()
        data['name'] = args.sensor.lower()
        data['timestamp'] = str(datetime.now())
        data['measurements'] = {}
        for key, value in sorted(sensor_data.items()):
           data['measurements'][key] = value

        out = ''
        if args.format == 'json':
            out = self._generate_json(args, data)
        elif args.format == 'xml':
            out = self._generate_xml(args, data)
        else:
            out = self._generate_text(args, data)

        print(out)

    def _generate_json(self, args, data):
        indent = 4 if args.pretty_print else None
        json_data = json.dumps(data, indent=indent)
        return json_data

    def _generate_xml(self, args, data):
        xml = dicttoxml(data, attr_type=False, custom_root='sensor')
        if args.pretty_print:
            dom = parseString(xml)
            return dom.toprettyxml()
        else:
            return xml

    def _generate_text(self, args, data):
        out = "timestamp: {}\n".format(data['timestamp'])
        for key, value in data['measurements'].items():
            out += "{}: {}\n".format(key, value)
        return out


class SensorNode(Application):
   
    DESCRIPTION = """sennode - Basic node application for exposing an I2C sensor 
    via HTTP, WebSockets or MQTT"""

    def __init__(self, loop=None, client=None, miner=None):
        super().__init__(loop, client)
        self._webserver = None
        self._publisher = None
        
        print("Enter Ctrl-C to exit.")

        from senlib.web import WebServer
        self._webserver = WebServer(self._args.interval, self._loop, self._sensor)
        http_host, http_port = self._args.http_address, self._args.http_port

        print("HTTP server runs under http://{}:{}".format(http_host, http_port))
        print("Websocket server runs under ws://{}:{}".format(http_host, http_port))
        h = self._webserver.make_handler()
        f = self._loop.create_server(h, http_host, http_port)
        self._loop.run_until_complete(f)

        if self._args.mqtt_address:
            from senlib.mqtt import Publisher
            mqtt_host, mqtt_port, mqtt_topic = self._args.mqtt_address, self._args.mqtt_port, self._args.mqtt_topic
            if not mqtt_topic:
                mqtt_topic = 'sensor/{}'.format(self._sensor.DRIVER_NAME)

            self._publisher = Publisher(mqtt_host, mqtt_port, mqtt_topic)
            async def connect():
                code = await self._publisher.connect()
                if code == 0:
                    print("Connected to MQTT broker {}:{}".format(mqtt_host, mqtt_port))
                    print("Publish data under topic {}".format(mqtt_topic))

            asyncio.ensure_future(connect())

    def _add_extra_arguments(self):
        self._parser.add_argument('-i', '--interval', type=float, dest='interval', 
                help='Set sampling interval.', default=2)
        self._parser.add_argument('--http-address', type=str, dest='http_address', 
                help='Set HTTP address.', default='0.0.0.0')
        self._parser.add_argument('--http-port', type=int, dest='http_port', 
                help='Set HTTP port.', default=8080)
        self._parser.add_argument('--mqtt-address', type=str, dest='mqtt_address', 
                help='Set MQTT broker address.', default='')
        self._parser.add_argument('--mqtt-port', type=int, dest='mqtt_port', 
                help='Set MQTT broker port.', default=1883)
        self._parser.add_argument('--mqtt-topic', type=str, dest='mqtt_topic', 
                help='Set MQTT topic.', default='')
 
    def _handle_data(self, data):
        if self._webserver:
            self._webserver.broadcast(data)
        
        if self._publisher:
            self._publisher.publish(data)

    def _after_stop(self):
        if self._publisher:
            self._publisher.disconnect()



def senlib():
    app = SenlibCLI()
    app.run()

def sennode():
    app = SensorNode()
    app.run()


