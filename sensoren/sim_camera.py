import json
import os
import time
import random
from urllib import request as urlreq

from http_utils import post_json
from mqtt_utils import build_client, publish_event

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


def register_with_retry(retries=10, delay=3):
    for i in range(retries):
        try:
            post_json(HOST + '/unit', CAMERA)
            print('camera registered')
            return
        except Exception as exc:
            print(f'camera register attempt {i+1} failed: {exc}')
            time.sleep(delay)


def fetch_map():
    try:
        with urlreq.urlopen(HOST + '/map', timeout=2) as resp:
            return json.load(resp)
    except Exception:
        return None


def cell_is_sand(map_data, mx, my):
    if not map_data:
        return True
    w = map_data.get('width', 0)
    h = map_data.get('height', 0)
    if mx < 0 or my < 0 or mx >= w or my >= h:
        return False
    idx = my * w + mx
    return map_data.get('cells', [])[idx].get('type') in {'sand', 'sand_light'}


def run():
    mqtt_client = build_client(f'{UNIT_ID}-pub')
    register_with_retry()

    while True:
        register()
        map_data = fetch_map()

        if random.random() < 0.15 and cell_is_sand(map_data, CAM_X, CAM_Y):
            event = {
                'unit_id': UNIT_ID,
                'type': 'blocked_route',
                'description': 'obstacle on path',
                'x': CAM_X,
                'y': CAM_Y,
                'priority': 2,
                'timestamp': int(time.time()),
            }
            publish_event(mqtt_client, UNIT_ID, event)
            # HTTP fallback
            try:
                post_json(HOST + '/incident', event)
            except Exception:
                pass
            print('camera reported blocked_route via MQTT')
        else:
            conf = round(random.uniform(0.6, 0.99), 2)
            event = {
                'unit_id': UNIT_ID,
                'type': 'person_detected',
                'confidence': conf,
                'x': CAM_X,
                'y': CAM_Y,
                'priority': 1,
                'timestamp': int(time.time()),
            }
            publish_event(mqtt_client, UNIT_ID, event)
            try:
                post_json(HOST + '/incident', event)
            except Exception:
                pass
            print('camera reported person_detected', conf, 'via MQTT')

        time.sleep(REPORT_INTERVAL)


if __name__ == '__main__':
    run()
