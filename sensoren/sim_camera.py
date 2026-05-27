import os
import random
import time

import requests

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
CAMERA = {'id': 'camera-1', 'role': 'camera', 'x': 13, 'y': 9}


def register():
    try:
        requests.post(HOST + '/unit', json=CAMERA, timeout=2)
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
        person_confidence = random.random()
        print('person confidence:', person_confidence)
        if person_confidence > 0.95:
            send_incident({
                'type': 'person_detected',
                'confidence': person_confidence,
                'x': CAMERA['x'],
                'y': CAMERA['y'],
                'priority': 1,
            })

        if random.random() < 0.05:
            send_incident({
                'type': 'blocked_route',
                'description': 'debris',
                'x': 12,
                'y': 10,
                'priority': 2,
            })

        time.sleep(2)


if __name__ == '__main__':
    run()