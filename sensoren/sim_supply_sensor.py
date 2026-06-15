import os
import time
import random
import json
from urllib import request as urlreq

from http_utils import post_json

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
UNIT_ID = os.environ.get('UNIT_ID', 'supply-sensor-1')
REPORT_INTERVAL = int(os.environ.get('REPORT_INTERVAL', '12'))
S_X = int(os.environ.get('S_X', '14'))
S_Y = int(os.environ.get('S_Y', '8'))

SENSOR = {
    'id': UNIT_ID,
    'role': 'supply_sensor',
    'x': S_X,
    'y': S_Y,
    'state': 'IDLE',
}


def register():
    try:
        post_json(HOST + '/unit', SENSOR)
    except Exception as exc:
        print('supply sensor register failed', exc)


def run():
    register()
    while True:
        register()
        # simulate supply level percent
        level = random.randint(5, 100)
        try:
            # fetch map and only post low_stock if sensor is on sand
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

            if level < 25 and cell_is_sand(S_X, S_Y):
                post_json(HOST + '/incident', {
                    'type': 'low_stock',
                    'value': level,
                    'x': S_X,
                    'y': S_Y,
                    'priority': 2,
                })
                print('supply sensor reported low_stock', level)
            else:
                # occasionally post a supply level reading
                if random.random() < 0.2:
                    post_json(HOST + '/incident', {
                        'type': 'supply_level',
                        'value': level,
                        'x': S_X,
                        'y': S_Y,
                        'priority': 3,
                    })
            
        except Exception as exc:
            print('supply sensor report failed', exc)
        time.sleep(REPORT_INTERVAL)


if __name__ == '__main__':
    run()
