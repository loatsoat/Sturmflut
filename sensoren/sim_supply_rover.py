import json
import os
import threading
import time
from concurrent import futures
from urllib import request as urlreq

from communication_router import CommunicationRouter
from coordination import RicartAgrawalaCoordinator
from http_utils import post_json
from mqtt_utils import build_client, publish_telemetry
from rpc_utils import load_grpc_support
from vehicle_utils import (
    fetch_map_once,
    find_nearest_land,
    register_unit,
    register_unit_with_retry,
    send_mission_update,
    start_charging_trigger_loop,
)

HOST     = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
UNIT_ID  = os.environ.get('UNIT_ID', 'supply-rover-1')
RPC_HOST = os.environ.get('RPC_HOST', '127.0.0.1')
RPC_PORT = int(os.environ.get('RPC_PORT', '50053'))

SUPPLY_ROVER = {
    'id':       UNIT_ID,
    'role':     'supply_rover',
    'x':        11,
    'y':        10,
    'rpc_host': RPC_HOST,
    'rpc_port': RPC_PORT,
    'state':    'IDLE',
}
STATE = {'value': 'IDLE'}
GRPC, ASSIGNMENT_PB2, ASSIGNMENT_PB2_GRPC = load_grpc_support(
    os.path.dirname(os.path.abspath(__file__))
)

_mqtt        = None
_COORDINATOR = None
_ROUTER      = None


def _telemetry_payload():
    return {
        'unit_id':   UNIT_ID,
        'role':      'supply_rover',
        'x':         SUPPLY_ROVER['x'],
        'y':         SUPPLY_ROVER['y'],
        'state':     STATE['value'],
        'rpc_host':  RPC_HOST,
        'rpc_port':  RPC_PORT,
        'timestamp': int(time.time()),
    }


def _send_update(mission_id, state, message):
    send_mission_update(UNIT_ID, HOST, _mqtt, _ROUTER, mission_id, state, message)


def _cell_type_at(map_data, mx, my):
    if not map_data:
        return None
    w = map_data.get('width', 0)
    h = map_data.get('height', 0)
    if mx < 0 or my < 0 or mx >= w or my >= h:
        return 'water'
    try:
        return map_data.get('cells', [])[my * w + mx].get('type')
    except Exception:
        return None


def move_towards_target(target_x, target_y, mission_id=None):
    try:
        with urlreq.urlopen(HOST + '/map', timeout=2) as resp:
            map_data = json.load(resp)
    except Exception:
        map_data = None

    while SUPPLY_ROVER['x'] != target_x or SUPPLY_ROVER['y'] != target_y:
        next_x = SUPPLY_ROVER['x']
        next_y = SUPPLY_ROVER['y']
        if SUPPLY_ROVER['x'] < target_x:
            next_x += 1
        elif SUPPLY_ROVER['x'] > target_x:
            next_x -= 1
        if SUPPLY_ROVER['y'] < target_y:
            next_y += 1
        elif SUPPLY_ROVER['y'] > target_y:
            next_y -= 1

        if _cell_type_at(map_data, next_x, next_y) == 'water':
            _send_update(mission_id or '', 'ERROR', f'blocked by water at ({next_x},{next_y})')
            STATE['value'] = 'IDLE'
            return

        SUPPLY_ROVER['x'] = next_x
        SUPPLY_ROVER['y'] = next_y
        SUPPLY_ROVER['state'] = STATE['value']
        register_unit(SUPPLY_ROVER, HOST)
        if _mqtt:
            publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(0.5)


def simulate_supply_work(mission_id, incident_type, x, y):
    STATE['value'] = 'BUSY'
    _send_update(mission_id, 'BUSY', f'supply rover delivering to ({x},{y}) for {incident_type}')
    move_towards_target(x, y, mission_id)
    time.sleep(1.8)
    _send_update(mission_id, 'DONE', 'delivery complete')
    # 4.4 – charging station access requests, resource acquires then releases
    if _COORDINATOR:
        ok = _COORDINATOR.request_access('charging_station', timeout=30.0)
        if ok:
            time.sleep(2.0)
            _COORDINATOR.release_access()
    STATE['value'] = 'IDLE'


class SupplyAssignmentService(ASSIGNMENT_PB2_GRPC.VehicleAssignmentServicer):
    def AssignMission(self, request, context):
        if STATE['value'] not in {'IDLE', 'ASSIGNED'}:
            return ASSIGNMENT_PB2.AssignmentReply(
                accepted=False,
                message='supply rover not available',
                vehicle_state=STATE['value'],
            )
        STATE['value'] = 'ASSIGNED'
        _send_update(request.mission_id, 'ASSIGNED', 'supply rover accepted mission')
        threading.Thread(
            target=simulate_supply_work,
            args=(request.mission_id, request.incident_type, request.target_x, request.target_y),
            daemon=True,
        ).start()
        return ASSIGNMENT_PB2.AssignmentReply(
            accepted=True,
            message='supply mission accepted',
            vehicle_state='ASSIGNED',
        )


def start_rpc_server():
    if GRPC is None or ASSIGNMENT_PB2_GRPC is None:
        print('gRPC unavailable, supply rover RPC server not started')
        return None
    server = GRPC.server(futures.ThreadPoolExecutor(max_workers=4))
    ASSIGNMENT_PB2_GRPC.add_VehicleAssignmentServicer_to_server(SupplyAssignmentService(), server)
    server.add_insecure_port(f'0.0.0.0:{RPC_PORT}')
    server.start()
    print('supply rover rpc server started on', RPC_PORT)
    return server


def run():
    global _mqtt, _COORDINATOR, _ROUTER
    # 4.3 – MQTT client builds, router creates
    _mqtt        = build_client(f'{UNIT_ID}-pub')
    _ROUTER      = CommunicationRouter(mqtt_client=_mqtt, http_url=HOST)
    # 4.4 – Ricart/Agrawala coordinator creates, peers registers
    _COORDINATOR = RicartAgrawalaCoordinator(UNIT_ID, _mqtt, peers=[
        'drone-1', 'repair-rover-1', 'supply-rover-1',
    ])
    _COORDINATOR.start()

    threading.Thread(
        target=start_charging_trigger_loop,
        args=(UNIT_ID, _COORDINATOR, STATE),
        daemon=True,
    ).start()  # 4.4 – charging trigger loop starts, MQTT listens

    map_data = fetch_map_once(HOST)
    nx, ny = find_nearest_land(map_data, SUPPLY_ROVER['x'], SUPPLY_ROVER['y'])
    SUPPLY_ROVER['x'], SUPPLY_ROVER['y'] = nx, ny

    _rpc_server = start_rpc_server()
    register_unit_with_retry(SUPPLY_ROVER, HOST, 'supply rover')

    while True:
        SUPPLY_ROVER['state'] = STATE['value']
        register_unit(SUPPLY_ROVER, HOST)
    # 4.3 – telemetry publishes via MQTT or router
        if _ROUTER:
            _ROUTER.send('telemetry', _telemetry_payload(), prefer='auto')
        else:
            publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(4)


if __name__ == '__main__':
    run()
