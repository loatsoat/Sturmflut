"""Shared utilities for vehicle simulators (drone, repair rover, supply rover)."""

import json
import os
import time
from collections import deque
from urllib import request as urlreq

import paho.mqtt.client as paho_mqtt

from http_utils import post_json
from mqtt_utils import publish_mission


def send_mission_update(unit_id, host, mqtt_client, router, mission_id, state, message):
    """Send a mission state update via router, MQTT, or HTTP fallback."""
    payload = {
        'mission_id': mission_id,
        'unit_id':    unit_id,
        'state':      state,
        'message':    message,
        'timestamp':  int(time.time()),
    }
    if router:
        result = router.send('mission', payload, prefer='auto')
        if not result.get('ok'):
            print(f'[{unit_id}] mission update failed: {result.get("error")}')
    else:
        if mqtt_client:
            publish_mission(mqtt_client, unit_id, payload)
        try:
            post_json(host + '/mission_update', payload)
        except Exception as exc:
            print(f'[{unit_id}] mission update failed: {exc}')


def register_unit(unit_dict, host):
    """Fire-and-forget registration of a unit with the Leitstelle."""
    try:
        post_json(host + '/unit', unit_dict)
    except Exception:
        pass


def register_unit_with_retry(unit_dict, host, label, retries=10, delay=3):
    """Register a unit with the Leitstelle, retrying on failure."""
    for i in range(retries):
        try:
            post_json(host + '/unit', unit_dict)
            print(f'{label} registered')
            return
        except Exception as exc:
            print(f'{label} register attempt {i + 1} failed: {exc}')
            time.sleep(delay)


def fetch_map_once(host):
    """Fetch the map from the Leitstelle once. Returns None on failure."""
    try:
        with urlreq.urlopen(host + '/map', timeout=2) as resp:
            return json.load(resp)
    except Exception:
        return None


def find_nearest_land(map_data, sx, sy):
    """BFS from (sx, sy) to find the nearest sand cell.

    Returns (sx, sy) unchanged if the start is already on land or map is None.
    """
    if not map_data:
        return sx, sy

    w     = map_data.get('width', 0)
    h     = map_data.get('height', 0)
    cells = map_data.get('cells', [])

    def cell_type(mx, my):
        if mx < 0 or my < 0 or mx >= w or my >= h:
            return 'water'
        return cells[my * w + mx].get('type')

    if cell_type(sx, sy) != 'water':
        return sx, sy

    q    = deque([(sx, sy)])
    seen = {(sx, sy)}
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            t = cell_type(nx, ny)
            if t in {'sand', 'sand_light'}:
                return nx, ny
            q.append((nx, ny))
    return sx, sy


def start_charging_trigger_loop(unit_id, coordinator, state_dict):
    """Connect to MQTT and listen for charging/trigger/<unit_id>.

    When triggered, requests access to the charging station via the
    Ricart/Agrawala coordinator. Intended to be run in a daemon thread.
    """
    broker = os.environ.get('MQTT_BROKER', '127.0.0.1')
    port   = int(os.environ.get('MQTT_PORT', '1883'))

    client = paho_mqtt.Client(client_id=f'{unit_id}-trigger-sub', clean_session=True)

    def on_message(_c, _u, msg):
        if coordinator and state_dict.get('value') == 'IDLE':
            print(f'[{unit_id}] charging trigger received, requesting access')
            ok = coordinator.request_access('charging_station', timeout=30.0)
            if ok:
                time.sleep(2.0)
                coordinator.release_access()

    client.on_message = on_message
    client.on_connect = lambda c, *_: c.subscribe(f'charging/trigger/{unit_id}', qos=1)

    for _ in range(10):
        try:
            client.connect(broker, port, keepalive=30)
            client.loop_forever()
            return
        except Exception as exc:
            print(f'[{unit_id}] trigger-sub connect failed: {exc}')
            time.sleep(2)
