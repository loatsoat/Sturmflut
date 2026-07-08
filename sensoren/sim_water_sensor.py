import os
import time
import random

from http_utils import post_json
from mqtt_utils import build_client, publish_event

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

ALERT_THRESHOLD_CM = 80


def register():
    try:
        post_json(HOST + '/unit', WATER_SENSOR)
    except Exception as exc:
        print('water sensor register failed', exc)


def register_with_retry(retries=10, delay=3):
    for i in range(retries):
        try:
            post_json(HOST + '/unit', WATER_SENSOR)
            print('water sensor registered')
            return
        except Exception as exc:
            print(f'water sensor register attempt {i+1} failed: {exc}')
            time.sleep(delay)


def run():
    mqtt_client = build_client(f'{UNIT_ID}-pub')
    register_with_retry()

    while True:
        register()
        # Simulate raw sensor reading: 0–120 cm
        level_cm = round(random.uniform(0.0, 120.0), 1)

        event = {
            'unit_id': UNIT_ID,
            'type': 'water_level_alert' if level_cm > ALERT_THRESHOLD_CM else 'water_level_ok',
            'water_level_cm': level_cm,
            'x': WATER_X,
            'y': WATER_Y,
            'priority': 2 if level_cm > ALERT_THRESHOLD_CM else 3,
            'timestamp': int(time.time()),
        }

        publish_event(mqtt_client, UNIT_ID, event)
        # HTTP fallback – only forward actual alerts
        if event['type'] == 'water_level_alert':
            try:
                post_json(HOST + '/incident', event)
            except Exception:
                pass
        print(f'water sensor reported level={level_cm} cm  type={event["type"]}')

        time.sleep(REPORT_INTERVAL)


if __name__ == '__main__':
    run()
