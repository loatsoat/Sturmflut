import os
import time
import random

from http_utils import post_json

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
UNIT_ID = os.environ.get('UNIT_ID', 'camera-1')
REPORT_INTERVAL = int(os.environ.get('REPORT_INTERVAL', '10'))
CAM_X = int(os.environ.get('CAM_X', '15'))
CAM_Y = int(os.environ.get('CAM_Y', '6'))

CAMERA = {
    'id': UNIT_ID,
    'role': 'camera',
    'x': CAM_X,
    'y': CAM_Y,
    'state': 'IDLE',
}


def register():
    try:
        post_json(HOST + '/unit', CAMERA)
    except Exception as exc:
        print('camera register failed', exc)


def run():
    register()
    while True:
        register()
        conf = round(random.uniform(0.6, 0.99), 2)
        try:
            post_json(HOST + '/incident', {
                'type': 'person_detected',
                'confidence': conf,
                'x': CAM_X,
                'y': CAM_Y,
                'priority': 1,
            })
            print('camera reported person_detected', conf)
        except Exception as exc:
            print('camera report failed', exc)
        time.sleep(REPORT_INTERVAL)


if __name__ == '__main__':
    run()