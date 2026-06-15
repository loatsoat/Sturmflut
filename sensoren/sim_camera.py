import os
import time
import random
import json
from urllib import request as urlreq

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
            # fetch map and only report blocked_route if the camera is on sand
            try:
                with urlreq.urlopen(HOST + '/map', timeout=2) as resp:
                    map_data = json.load(resp)
            except Exception:
                map_data = None

            def cell_is_sand(mx, my):
                if not map_data:
                    return True
                w = map_data.get('width', 0)
                h = map_data.get('height', 0)
                if mx < 0 or my < 0 or mx >= w or my >= h:
                    return False
                idx = my * w + mx
                return map_data.get('cells', [])[idx].get('type') in {'sand', 'sand_light'}

            if random.random() < 0.15 and cell_is_sand(CAM_X, CAM_Y):
                desc = 'obstacle on path'
                post_json(HOST + '/incident', {
                    'type': 'blocked_route',
                    'description': desc,
                    'x': CAM_X,
                    'y': CAM_Y,
                    'priority': 2,
                })
                print('camera reported blocked_route')
            else:
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