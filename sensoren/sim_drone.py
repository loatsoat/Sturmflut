import os
import threading
import time
from concurrent import futures

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
UNIT_ID  = os.environ.get('UNIT_ID', 'drone-1')
RPC_HOST = os.environ.get('RPC_HOST', '127.0.0.1')
RPC_PORT = int(os.environ.get('RPC_PORT', '50051'))

DRONE = {
    'id':       UNIT_ID,
    'role':     'drone',
    'x':        13,
    'y':        9,
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
        'role':      'drone',
        'x':         DRONE['x'],
        'y':         DRONE['y'],
        'state':     STATE['value'],
        'rpc_host':  RPC_HOST,
        'rpc_port':  RPC_PORT,
        'timestamp': int(time.time()),
    }


def _send_update(mission_id, state, message):
    send_mission_update(UNIT_ID, HOST, _mqtt, _ROUTER, mission_id, state, message)


def move_towards_target(target_x, target_y):
    while DRONE['x'] != target_x or DRONE['y'] != target_y:
        if DRONE['x'] < target_x:
            DRONE['x'] += 1
        elif DRONE['x'] > target_x:
            DRONE['x'] -= 1
        if DRONE['y'] < target_y:
            DRONE['y'] += 1
        elif DRONE['y'] > target_y:
            DRONE['y'] -= 1
        DRONE['state'] = STATE['value']
        register_unit(DRONE, HOST)
        if _mqtt:
            publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(0.5)


def simulate_drone_work(mission_id, incident_type, x, y):
    STATE['value'] = 'BUSY'
    _send_update(mission_id, 'BUSY', f'drone flying to ({x},{y}) for {incident_type}')
    move_towards_target(x, y)
    time.sleep(1.2)
    _send_update(mission_id, 'DONE', 'inspection complete')
    # 4.4 – charging station access requests, resource acquires then releases
    if _COORDINATOR:
        ok = _COORDINATOR.request_access('charging_station', timeout=30.0)
        if ok:
            time.sleep(2.0)
            _COORDINATOR.release_access()
    STATE['value'] = 'IDLE'


class DroneAssignmentService(ASSIGNMENT_PB2_GRPC.VehicleAssignmentServicer):
    def AssignMission(self, request, context):
        if STATE['value'] not in {'IDLE', 'ASSIGNED'}:
            return ASSIGNMENT_PB2.AssignmentReply(
                accepted=False,
                message='drone not available',
                vehicle_state=STATE['value'],
            )
        STATE['value'] = 'ASSIGNED'
        _send_update(request.mission_id, 'ASSIGNED', 'drone accepted mission')
        threading.Thread(
            target=simulate_drone_work,
            args=(request.mission_id, request.incident_type, request.target_x, request.target_y),
            daemon=True,
        ).start()
        return ASSIGNMENT_PB2.AssignmentReply(
            accepted=True,
            message='drone mission accepted',
            vehicle_state='ASSIGNED',
        )


def start_rpc_server():
    if GRPC is None or ASSIGNMENT_PB2_GRPC is None:
        print('gRPC unavailable, drone RPC server not started')
        return None
    server = GRPC.server(futures.ThreadPoolExecutor(max_workers=4))
    ASSIGNMENT_PB2_GRPC.add_VehicleAssignmentServicer_to_server(DroneAssignmentService(), server)
    server.add_insecure_port(f'0.0.0.0:{RPC_PORT}')
    server.start()
    print('drone rpc server started on', RPC_PORT)
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
    nx, ny = find_nearest_land(map_data, DRONE['x'], DRONE['y'])
    DRONE['x'], DRONE['y'] = nx, ny

    _rpc_server = start_rpc_server()
    register_unit_with_retry(DRONE, HOST, 'drone')

    while True:
        DRONE['state'] = STATE['value']
        register_unit(DRONE, HOST)
    # 4.3 – telemetry publishes via MQTT or router
        if _ROUTER:
            _ROUTER.send('telemetry', _telemetry_payload(), prefer='auto')
        else:
            publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(2)


if __name__ == '__main__':
    run()
