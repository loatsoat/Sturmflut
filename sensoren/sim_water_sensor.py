import os
import time
import random

from http_utils import post_json

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
UNIT_ID = os.environ.get('UNIT_ID', 'water-sensor-1')
REPORT_INTERVAL = int(os.environ.get('REPORT_INTERVAL', '8'))
WATER_X = int(os.environ.get('WATER_X', '5'))
WATER_Y = int(os.environ.get('WATER_Y', '5'))

WATER_SENSOR = {
    'id': UNIT_ID,
    'role': 'water_sensor',
    'x': WATER_X,
    'y': WATER_Y,
    'state': 'IDLE',
}


def register():
    try:
        post_json(HOST + '/unit', WATER_SENSOR)
    except Exception as exc:
        print('water sensor register failed', exc)


def run():
    register()
    while True:
        register()
        level = round(random.uniform(0.0, 10.0), 2)
        try:
            post_json(HOST + '/incident', {
                'type': 'water_level_alert',
                'value': level,
                'x': 5,
                'y': 5,
                'priority': 2,
            })
            print('reported water level', level)
        except Exception as exc:
            print('water report failed', exc)
        time.sleep(REPORT_INTERVAL)


if __name__ == '__main__':
    run()