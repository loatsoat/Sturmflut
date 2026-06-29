import json
import os
import time
import random
from urllib import request as urlreq

from http_utils import post_json
from mqtt_utils import build_client, publish_event

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

LOW_STOCK_THRESHOLD = 20


def register():
    try:
        post_json(HOST + '/unit', SENSOR)
    except Exception as exc:
        print('supply sensor register failed', exc)


def register_with_retry(retries=10, delay=3):
    for i in range(retries):
        try:
            post_json(HOST + '/unit', SENSOR)
            print('supply sensor registered')
            return
        except Exception as exc:
            print(f'supply sensor register attempt {i+1} failed: {exc}')
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
        level = random.randint(5, 100)
        map_data = fetch_map()
        on_land = cell_is_sand(map_data, S_X, S_Y)

        if level < LOW_STOCK_THRESHOLD and on_land:
            event = {
                'unit_id': UNIT_ID,
                'type': 'low_stock',
                'supply_level_percent': level,
                'x': S_X,
                'y': S_Y,
                'priority': 2,
                'timestamp': int(time.time()),
            }
            publish_event(mqtt_client, UNIT_ID, event)
            try:
                post_json(HOST + '/incident', event)
            except Exception:
                pass
            print(f'supply sensor reported low_stock level={level}% via MQTT')
        else:
            # Periodic status reading (not an alert)
            if random.random() < 0.2:
                event = {
                    'unit_id': UNIT_ID,
                    'type': 'supply_level',
                    'supply_level_percent': level,
                    'x': S_X,
                    'y': S_Y,
                    'priority': 3,
                    'timestamp': int(time.time()),
                }
                publish_event(mqtt_client, UNIT_ID, event)
                try:
                    post_json(HOST + '/incident', event)
                except Exception:
                    pass

        time.sleep(REPORT_INTERVAL)


if __name__ == '__main__':
    run()
