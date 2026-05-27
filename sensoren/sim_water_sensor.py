import os
import random
import time

import requests

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
SENSOR = {'id': 'water-sensor-1', 'role': 'water_sensor', 'x': 8, 'y': 12}


def register():
    try:
        requests.post(HOST + '/unit', json=SENSOR, timeout=2)
    except Exception:
        pass


def send_incident(payload):
    try:
        requests.post(HOST + '/incident', json=payload, timeout=2)
        print('sent incident', payload)
    except Exception as exc:
        print('send failed', exc)


def run():
    register()
    while True:
        level = random.gauss(50, 20)
        print('water level:', level)
        if level > 90:
            send_incident({
                'type': 'water_level_alert',
                'value': level,
                'x': SENSOR['x'],
                'y': SENSOR['y'],
                'priority': 2,
            })
        time.sleep(3)


if __name__ == '__main__':
    run()