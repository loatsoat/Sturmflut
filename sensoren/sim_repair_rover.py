import json
import os
import threading
import time
from collections import deque
from concurrent import futures
from urllib import request as urlreq

from http_utils import post_json
from mqtt_utils import build_client, publish_telemetry, publish_mission
from rpc_utils import load_grpc_support

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
UNIT_ID = os.environ.get('UNIT_ID', 'repair-rover-1')
RPC_HOST = os.environ.get('RPC_HOST', '127.0.0.1')
RPC_PORT = int(os.environ.get('RPC_PORT', '50052'))

REPAIR_ROVER = {
    'id': UNIT_ID,
    'role': 'repair_rover',
    'x': 8,
    'y': 12,
    'rpc_host': RPC_HOST,
    'rpc_port': RPC_PORT,
    'state': 'IDLE',
}
STATE = {'value': 'IDLE'}
GRPC, ASSIGNMENT_PB2, ASSIGNMENT_PB2_GRPC = load_grpc_support(os.path.dirname(os.path.abspath(__file__)))

_mqtt = None  # set in run()


def _telemetry_payload():
    return {
        'unit_id': UNIT_ID,
        'role': 'repair_rover',
        'x': REPAIR_ROVER['x'],
        'y': REPAIR_ROVER['y'],
        'state': STATE['value'],
        'timestamp': int(time.time()),
    }


def move_towards_target(target_x, target_y, mission_id=None):
    try:
        with urlreq.urlopen(HOST + '/map', timeout=2) as resp:
            map_data = json.load(resp)
    except Exception:
        map_data = None

    def cell_type_at(mx, my):
        if not map_data:
            return None
        if mx < 0 or my < 0 or mx >= map_data.get('width', 0) or my >= map_data.get('height', 0):
            return 'water'
        idx = my * map_data.get('width') + mx
        try:
            return map_data.get('cells', [])[idx].get('type')
        except Exception:
            return None

    while REPAIR_ROVER['x'] != target_x or REPAIR_ROVER['y'] != target_y:
        next_x = REPAIR_ROVER['x']
        next_y = REPAIR_ROVER['y']
        if REPAIR_ROVER['x'] < target_x:
            next_x += 1
        elif REPAIR_ROVER['x'] > target_x:
            next_x -= 1
        if REPAIR_ROVER['y'] < target_y:
            next_y += 1
        elif REPAIR_ROVER['y'] > target_y:
            next_y -= 1

        next_type = cell_type_at(next_x, next_y)
        if next_type == 'water':
            send_mission_update(mission_id or '', 'ERROR', f'blocked by water at ({next_x},{next_y})')
            STATE['value'] = 'IDLE'
            return

        REPAIR_ROVER['x'] = next_x
        REPAIR_ROVER['y'] = next_y
        register()
        if _mqtt:
            publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(0.5)


def fetch_map_once():
    try:
        with urlreq.urlopen(HOST + '/map', timeout=2) as resp:
            return json.load(resp)
    except Exception:
        return None


def find_nearest_land(map_data, sx, sy):
    if not map_data:
        return sx, sy
    w = map_data.get('width', 0)
    h = map_data.get('height', 0)
    cells = map_data.get('cells', [])

    def cell_type(mx, my):
        if mx < 0 or my < 0 or mx >= w or my >= h:
            return 'water'
        idx = my * w + mx
        return cells[idx].get('type')

    if cell_type(sx, sy) != 'water':
        return sx, sy

    q = deque([(sx, sy)])
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


def send_mission_update(mission_id, state, message):
    payload = {
        'mission_id': mission_id,
        'unit_id': UNIT_ID,
        'state': state,
        'message': message,
        'timestamp': int(time.time()),
    }
    if _mqtt:
        publish_mission(_mqtt, UNIT_ID, payload)
    try:
        post_json(HOST + '/mission_update', payload)
    except Exception as exc:
        print('mission update failed', exc)


def simulate_repair_work(mission_id, incident_type, x, y):
    STATE['value'] = 'BUSY'
    send_mission_update(mission_id, 'BUSY', f'repair rover driving to ({x},{y}) for {incident_type}')
    move_towards_target(x, y, mission_id)
    time.sleep(1.5)
    send_mission_update(mission_id, 'DONE', 'repair complete')
    STATE['value'] = 'IDLE'


class RepairAssignmentService(ASSIGNMENT_PB2_GRPC.VehicleAssignmentServicer):
    def AssignMission(self, request, context):
        if STATE['value'] not in {'IDLE', 'ASSIGNED'}:
            return ASSIGNMENT_PB2.AssignmentReply(
                accepted=False,
                message='repair rover not available',
                vehicle_state=STATE['value'],
            )
        STATE['value'] = 'ASSIGNED'
        send_mission_update(request.mission_id, 'ASSIGNED', 'repair rover accepted mission')
        threading.Thread(
            target=simulate_repair_work,
            args=(request.mission_id, request.incident_type, request.target_x, request.target_y),
            daemon=True,
        ).start()
        return ASSIGNMENT_PB2.AssignmentReply(
            accepted=True,
            message='repair mission accepted',
            vehicle_state='ASSIGNED',
        )


def start_rpc_server():
    if GRPC is None or ASSIGNMENT_PB2_GRPC is None:
        print('gRPC unavailable, repair rover RPC server not started')
        return None
    server = GRPC.server(futures.ThreadPoolExecutor(max_workers=4))
    ASSIGNMENT_PB2_GRPC.add_VehicleAssignmentServicer_to_server(RepairAssignmentService(), server)
    server.add_insecure_port(f'0.0.0.0:{RPC_PORT}')
    server.start()
    print('repair rover rpc server started on', RPC_PORT)
    return server


def register():
    try:
        REPAIR_ROVER['state'] = STATE['value']
        post_json(HOST + '/unit', REPAIR_ROVER)
    except Exception:
        pass


def register_with_retry(retries=10, delay=3):
    for i in range(retries):
        try:
            REPAIR_ROVER['state'] = STATE['value']
            post_json(HOST + '/unit', REPAIR_ROVER)
            print('repair rover registered')
            return
        except Exception as exc:
            print(f'repair rover register attempt {i+1} failed: {exc}')
            time.sleep(delay)


def run():
    global _mqtt
    _mqtt = build_client(f'{UNIT_ID}-pub')
    rpc_server = start_rpc_server()
    map_data = fetch_map_once()
    nx, ny = find_nearest_land(map_data, REPAIR_ROVER['x'], REPAIR_ROVER['y'])
    REPAIR_ROVER['x'] = nx
    REPAIR_ROVER['y'] = ny
    register_with_retry()

    while True:
        register()
        publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(3)

    rpc_server.stop(grace=0)


if __name__ == '__main__':
    run()
