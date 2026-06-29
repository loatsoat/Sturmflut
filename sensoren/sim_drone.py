import os
import threading
import time
from concurrent import futures

from http_utils import post_json
from mqtt_utils import build_client, publish_telemetry, publish_mission
from rpc_utils import load_grpc_support

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
UNIT_ID = os.environ.get('UNIT_ID', 'drone-1')
RPC_HOST = os.environ.get('RPC_HOST', '127.0.0.1')
RPC_PORT = int(os.environ.get('RPC_PORT', '50051'))

DRONE = {
    'id': UNIT_ID,
    'role': 'drone',
    'x': 13,
    'y': 9,
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
        'role': 'drone',
        'x': DRONE['x'],
        'y': DRONE['y'],
        'state': STATE['value'],
        'timestamp': int(time.time()),
    }


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
        register()
        if _mqtt:
            publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(0.5)


def send_mission_update(mission_id, state, message):
    payload = {
        'mission_id': mission_id,
        'unit_id': UNIT_ID,
        'state': state,
        'message': message,
        'timestamp': int(time.time()),
    }
    # MQTT primary
    if _mqtt:
        publish_mission(_mqtt, UNIT_ID, payload)
    # HTTP fallback
    try:
        post_json(HOST + '/mission_update', payload)
    except Exception as exc:
        print('mission update failed', exc)


def simulate_drone_work(mission_id, incident_type, x, y):
    STATE['value'] = 'BUSY'
    send_mission_update(mission_id, 'BUSY', f'drone flying to ({x},{y}) for {incident_type}')
    move_towards_target(x, y)
    time.sleep(1.2)
    send_mission_update(mission_id, 'DONE', 'inspection complete')
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
        send_mission_update(request.mission_id, 'ASSIGNED', 'drone accepted mission')
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


def register():
    try:
        DRONE['state'] = STATE['value']
        post_json(HOST + '/unit', DRONE)
    except Exception:
        pass


def register_with_retry(retries=10, delay=3):
    for i in range(retries):
        try:
            DRONE['state'] = STATE['value']
            post_json(HOST + '/unit', DRONE)
            print('drone registered')
            return
        except Exception as exc:
            print(f'drone register attempt {i+1} failed: {exc}')
            time.sleep(delay)


def run():
    global _mqtt
    _mqtt = build_client(f'{UNIT_ID}-pub')
    rpc_server = start_rpc_server()
    register_with_retry()

    while True:
        register()
        publish_telemetry(_mqtt, UNIT_ID, _telemetry_payload())
        time.sleep(2)

    rpc_server.stop(grace=0)


if __name__ == '__main__':
    run()
