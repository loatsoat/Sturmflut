import json
import math
import os
import socket
import threading
import time

import paho.mqtt.client as mqtt

from rpc_utils import load_grpc_support

MAP_FILE = 'map.json'
MAP_STYLE = 'island-v2'
MAP_WIDTH = 20
MAP_HEIGHT = 20
MAP_VERSION = 8
RPC_TIMEOUT_SECONDS = 2.0

VEHICLE_STATES = {'IDLE', 'ASSIGNED', 'BUSY', 'ERROR'}

MQTT_BROKER = os.environ.get('MQTT_BROKER', '127.0.0.1')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))

# Drop duplicate events within this window (seconds)
DEDUP_WINDOW_SECONDS = 15
# Drop events older than this (seconds)
STALE_THRESHOLD_SECONDS = 60


class Leitstelle:
    def __init__(self):
        self.map = self.load_map()
        self.units = {}
        self.incidents = []
        self.history = []
        self.active_missions = {}
        self.mission_log = []
        self.next_incident_id = 1
        self.next_mission_id = 1
        self.lock = threading.Lock()
        self._dedup_cache = {}
        self._position_lock = {}
        self.grpc, self.assignment_pb2, self.assignment_pb2_grpc = load_grpc_support(
            os.path.dirname(os.path.abspath(__file__))
        )
        threading.Thread(target=self.incident_processor, daemon=True).start()
        threading.Thread(target=self._start_mqtt, daemon=True).start()

    def _start_mqtt(self):
        client = mqtt.Client(client_id='leitstelle-sub', clean_session=True)
        client.on_connect = self._on_mqtt_connect
        client.on_message = self._on_mqtt_message
        client.reconnect_delay_set(min_delay=2, max_delay=30)
        for attempt in range(20):
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
                client.loop_forever()
                return
            except Exception as exc:
                print(f'[mqtt] connect attempt {attempt + 1} failed: {exc}')
                time.sleep(3)
        print('[mqtt] WARNING: could not connect – running without MQTT subscriber')

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        print(f'[mqtt] connected rc={rc}')
        client.subscribe('sensors/events/#', qos=1)
        client.subscribe('vehicles/telemetry/#', qos=0)
        client.subscribe('vehicles/missions/#', qos=1)

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except Exception:
            return
        topic = msg.topic
        if topic.startswith('sensors/events/'):
            self._handle_sensor_event(payload)
        elif topic.startswith('vehicles/telemetry/'):
            self._handle_vehicle_telemetry(payload)
        elif topic.startswith('vehicles/missions/'):
            self._handle_vehicle_mission(payload)

    def _is_stale(self, payload):
        ts = payload.get('timestamp')
        if ts and (int(time.time()) - int(ts)) > STALE_THRESHOLD_SECONDS:
            return True
        return False

    def _is_duplicate(self, payload):
        unit_id = payload.get('unit_id', '')
        evt_type = payload.get('type', '')
        x = payload.get('x', 0)
        y = payload.get('y', 0)
        key = (unit_id, evt_type, x, y)
        now = time.time()
        last = self._dedup_cache.get(key, 0)
        if now - last < DEDUP_WINDOW_SECONDS:
            return True
        self._dedup_cache[key] = now
        cutoff = now - DEDUP_WINDOW_SECONDS * 2
        self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if v > cutoff}
        return False

    def _handle_sensor_event(self, payload):
        if self._is_stale(payload):
            print('[mqtt] dropped stale sensor event')
            return
        if self._is_duplicate(payload):
            print('[mqtt] dropped duplicate sensor event')
            return

        incident_type = payload.get('type', '')

        if incident_type in {'water_level_ok', 'supply_level'}:
            return
        x = payload.get('x', 0)
        y = payload.get('y', 0)
        pos_key = (incident_type, x, y)
        with self.lock:
            if pos_key in self._position_lock:
                print(f'[mqtt] dropped – same position already active: {pos_key}')
                return
            incident = {
                'id': self.next_incident_id,
                'type': incident_type,
                'value': payload.get('value', ''),
                'raw': payload,
            }
            self.next_incident_id += 1
            self.incidents.append(incident)
            self._position_lock[pos_key] = incident['id']
        print(f'[mqtt] queued incident from MQTT: {incident_type} @ ({x},{y})')

    def _handle_vehicle_telemetry(self, payload):
        unit_id = payload.get('unit_id', '')
        if not unit_id:
            return
        with self.lock:
            if unit_id not in self.units:
                self.units[unit_id] = {
                    'id': unit_id,
                    'role': payload.get('role', 'vehicle'),
                    'state': payload.get('state', 'IDLE'),
                }
            unit = self.units[unit_id]
            unit['x'] = payload.get('x', unit.get('x'))
            unit['y'] = payload.get('y', unit.get('y'))
            if payload.get('role'):
                unit['role'] = payload['role']
            new_state = payload.get('state', '')
            if new_state in VEHICLE_STATES:
                unit['state'] = new_state

    def _handle_vehicle_mission(self, payload):
        mission_id = payload.get('mission_id', '')
        unit_id = payload.get('unit_id', '')
        new_state = payload.get('state', '').upper()
        message = payload.get('message', '')
        if new_state not in {'ASSIGNED', 'BUSY', 'DONE', 'IDLE', 'ERROR'}:
            return
        with self.lock:
            if unit_id in self.units and new_state in VEHICLE_STATES:
                self.units[unit_id]['state'] = new_state
            mission = self.active_missions.get(mission_id)
            if mission:
                mission['status'] = new_state
                mission['updated_at'] = int(time.time())
                self._log_mission(mission_id, unit_id, new_state, message)
                if new_state in {'DONE', 'ERROR'}:
                    # Release position lock for this mission
                    inc_type = mission.get('incident_type', '')
                    tx = mission.get('target_x', 0)
                    ty = mission.get('target_y', 0)
                    self._position_lock.pop((inc_type, tx, ty), None)
                    self.active_missions.pop(mission_id, None)

    def is_valid_map(self, data):
        if not isinstance(data, dict):
            return False
        if data.get('style') != MAP_STYLE:
            return False
        if data.get('version') != MAP_VERSION:
            return False
        if data.get('width') != MAP_WIDTH or data.get('height') != MAP_HEIGHT:
            return False
        cells = data.get('cells', [])
        if len(cells) != MAP_WIDTH * MAP_HEIGHT:
            return False
        cell_by_pos = {(cell.get('x'), cell.get('y')): cell for cell in cells}
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                cell = cell_by_pos.get((x, y))
                if not cell:
                    return False
                if x in (0, MAP_WIDTH - 1) or y in (0, MAP_HEIGHT - 1):
                    if cell.get('type') != 'water':
                        return False
                elif cell.get('type') not in {'sand', 'sand_light'}:
                    return False
        if not any(cell.get('infrastructure') == 'harbor' for cell in cells):
            return False
        return True

    def create_island_map(self):
        w, h = MAP_WIDTH, MAP_HEIGHT
        cells = []

        def terrain_noise(x, y):
            return ((x * 37 + y * 19 + x * y * 11) % 9) / 9.0

        for y in range(h):
            for x in range(w):
                if x in (0, w - 1) or y in (0, h - 1):
                    cell_type = 'water'
                else:
                    dx = abs(x - 15)
                    dy = abs(y - 5)
                    score = (dx / 5.8) + (dy / 3.8) + (terrain_noise(x, y) * 0.42)
                    spur = (x >= 17 and 5 <= y <= 9 and (x + y) % 2 == 0)
                    if score <= 0.98 or spur:
                        cell_type = 'sand'
                    elif score <= 1.62:
                        cell_type = 'sand_light'
                    else:
                        cell_type = 'water'
                cells.append({'x': x, 'y': y, 'type': cell_type})

        data = {'width': w, 'height': h, 'style': MAP_STYLE, 'version': MAP_VERSION, 'cells': cells}
        infrastructure = {
            (14, 6): 'helipad',
            (16, 7): 'bridge',
            (14, 8): 'depot',
            (13, 7): 'harbor',
            (16, 9): 'charging_station',
        }
        for (x, y), name in infrastructure.items():
            idx = y * w + x
            if 0 <= idx < len(data['cells']):
                data['cells'][idx]['infrastructure'] = name
        return data

    def load_map(self):
        try:
            with open(MAP_FILE, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
            if self.is_valid_map(data):
                return data
        except Exception:
            pass
        data = self.create_island_map()
        with open(MAP_FILE, 'w', encoding='utf-8') as handle:
            json.dump(data, handle)
        return data

    def _cell_at(self, x, y):
        if x < 0 or y < 0 or x >= self.map['width'] or y >= self.map['height']:
            return {'type': 'water'}
        idx = y * self.map['width'] + x
        return self.map['cells'][idx]
    
    def incident_processor(self):
        while True:
            inc = None
            with self.lock:
                if self.incidents:
                    inc = self.incidents.pop(0)
            if inc:
                print('Incident:', inc)
                self._process_incident(inc)
            time.sleep(1)

    def _process_incident(self, inc):
        try:
            raw = inc.get('raw', {}) if isinstance(inc.get('raw', {}), dict) else {}
            value = inc.get('value', '')
            if not value:
                if inc.get('type') == 'person_detected' and 'confidence' in raw:
                    value = f"confidence={raw.get('confidence')}"
                elif inc.get('type') in {'water_level_alert', 'water_level_ok'} and 'water_level_cm' in raw:
                    value = f"level={raw.get('water_level_cm')}cm"
                elif inc.get('type') == 'blocked_route' and raw.get('description'):
                    value = f"description={raw.get('description')}"
                elif inc.get('type') == 'low_stock' and 'supply_level_percent' in raw:
                    value = f"level={raw.get('supply_level_percent')}%"

            with self.lock:
                self.history.append({
                    'id': inc['id'],
                    'type': inc.get('type', ''),
                    'value': value,
                    'processed_at': int(time.time()),
                })

            self._dispatch_incident(inc)
        except Exception as exc:
            print('process incident failed:', exc)

    def _determine_role(self, incident_type, raw):
        if incident_type == 'person_detected':
            return 'drone'
        if incident_type in {'blocked_route', 'structure_damage'}:
            return 'repair_rover'
        if incident_type in {'low_stock', 'material_request'}:
            return 'supply_rover'
        x = raw.get('x')
        y = raw.get('y')
        if isinstance(x, int) and isinstance(y, int):
            cell = self._cell_at(x, y)
            if cell.get('type') == 'water':
                return 'drone'
        return None

    def _log_mission(self, mission_id, unit_id, state, message):
        self.mission_log.append({
            'mission_id': mission_id,
            'unit_id': unit_id,
            'state': state,
            'message': message,
            'timestamp': int(time.time()),
        })
        self.mission_log = self.mission_log[-200:]

    def _can_unit_reach(self, unit, x, y):
        role = unit.get('role')
        target_cell = self._cell_at(x, y)
        if role == 'drone':
            return True
        return target_cell.get('type') != 'water'

    def _select_unit_for_role(self, role, target_x, target_y):
        for uid, unit in sorted(self.units.items()):
            if unit.get('role') != role:
                continue
            if unit.get('state', 'IDLE') != 'IDLE':
                continue
            if not unit.get('rpc_port'):
                continue
            if not self._can_unit_reach(unit, target_x, target_y):
                continue
            return uid, unit
        return None, None

    def _assign_rpc(self, unit_id, unit, mission):
        if self.grpc is None:
            return False, 'gRPC stubs unavailable'
        host = unit.get('rpc_host') or unit_id
        port = unit.get('rpc_port')
        if not port:
            return False, 'Missing rpc_port on unit'
        endpoint = f"{host}:{port}"
        channel = self.grpc.insecure_channel(endpoint)
        stub = self.assignment_pb2_grpc.VehicleAssignmentStub(channel)
        req = self.assignment_pb2.AssignmentRequest(
            mission_id=mission['mission_id'],
            incident_type=mission['incident_type'],
            target_x=mission['target_x'],
            target_y=mission['target_y'],
            priority=mission['priority'],
        )
        try:
            reply = stub.AssignMission(req, timeout=RPC_TIMEOUT_SECONDS)
            if reply.accepted:
                return True, reply.message or 'accepted'
            return False, reply.message or 'rejected'
        except self.grpc.RpcError as exc:
            return False, f'rpc error: {exc.code().name}'
        except Exception as exc:
            return False, f'rpc failure: {exc}'
        finally:
            channel.close()

    def _dispatch_incident(self, incident):
        raw = incident.get('raw', {}) if isinstance(incident.get('raw', {}), dict) else {}
        role = self._determine_role(incident.get('type', ''), raw)
        if not role:
            return

        target_x = int(raw.get('x', 0)) if isinstance(raw.get('x', 0), (int, float)) else 0
        target_y = int(raw.get('y', 0)) if isinstance(raw.get('y', 0), (int, float)) else 0
        priority = int(raw.get('priority', 2)) if isinstance(raw.get('priority', 2), (int, float)) else 2

        with self.lock:
            mission_id = f"mission-{self.next_mission_id}"
            self.next_mission_id += 1
            mission = {
                'mission_id': mission_id,
                'incident_id': incident.get('id'),
                'incident_type': incident.get('type', ''),
                'target_x': target_x,
                'target_y': target_y,
                'priority': priority,
                'required_role': role,
                'status': 'QUEUED',
                'assigned_unit': '',
                'updated_at': int(time.time()),
            }
            self.active_missions[mission_id] = mission
            self._log_mission(mission_id, '', 'QUEUED', f"role={role}")

            uid, unit = self._select_unit_for_role(role, target_x, target_y)
            if not uid:
                mission['status'] = 'ERROR'
                mission['updated_at'] = int(time.time())
                self._log_mission(mission_id, '', 'ERROR', 'No matching IDLE unit found')
                pos_key = (incident.get('type', ''), target_x, target_y)
                self._position_lock.pop(pos_key, None)
                return
            unit['state'] = 'ASSIGNED'
            mission['assigned_unit'] = uid
            mission['status'] = 'ASSIGNED'
            mission['updated_at'] = int(time.time())
            self._log_mission(mission_id, uid, 'ASSIGNED', 'Dispatching via RPC')

        ok, message = self._assign_rpc(uid, unit, mission)

        with self.lock:
            current = self.active_missions.get(mission_id)
            if not current:
                return
            if ok:
                current['status'] = 'ASSIGNED'
                current['updated_at'] = int(time.time())
                self._log_mission(mission_id, uid, 'ASSIGNED', message)
            else:
                unit['state'] = 'ERROR'
                current['status'] = 'ERROR'
                current['updated_at'] = int(time.time())
                self._log_mission(mission_id, uid, 'ERROR', message)

    def handle_connection(self, conn, addr):
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = conn.recv(1024)
            if not chunk:
                break
            data += chunk
        header, _, rest = data.partition(b'\r\n\r\n')
        lines = header.decode(errors='ignore').split('\r\n')
        if not lines:
            conn.close(); return
        method, path = lines[0].split(' ')[0:2]
        headers = {}
        for l in lines[1:]:
            if ':' in l:
                k, v = l.split(':', 1); headers[k.strip().lower()] = v.strip()
        body = rest
        if 'content-length' in headers:
            need = int(headers['content-length']) - len(body)
            while need > 0:
                chunk = conn.recv(1024)
                if not chunk: break
                body += chunk; need -= len(chunk)

        try:
            if method == 'GET' and path == '/map':
                payload = json.dumps(self.map).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)

            elif method == 'GET' and path == '/status':
                payload = json.dumps({
                    'units': self.units,
                    'incidents': self.incidents,
                    'next_incident_id': self.next_incident_id,
                    'active_missions': list(self.active_missions.values()),
                    'mission_log': self.mission_log[-50:],
                }).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)

            elif method == 'GET' and path == '/history':
                payload = json.dumps({'history': self.history}).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)

            elif method == 'GET' and path == '/':
                payload = self._render_dashboard().encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)

            elif method == 'POST' and path == '/unit':
                obj = json.loads(body.decode() or '{}')
                uid = obj.get('id') or f'unit{len(self.units)+1}'
                role = obj.get('role', 'unit')
                obj['role'] = role
                if obj.get('state') not in VEHICLE_STATES:
                    obj['state'] = 'IDLE'
                self.units[uid] = obj
                payload = json.dumps({'result': 'registered', 'id': uid}).encode()
                conn.sendall(b'HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)

            elif method == 'POST' and path == '/incident':
                obj = json.loads(body.decode() or '{}')
                incident_type = obj.get('type', '')
                x = int(obj.get('x', 0)) if isinstance(obj.get('x', 0), (int, float)) else 0
                y = int(obj.get('y', 0)) if isinstance(obj.get('y', 0), (int, float)) else 0
                pos_key = (incident_type, x, y)
                with self.lock:
                    already_queued = pos_key in self._position_lock
                if already_queued:
                    payload = json.dumps({'result': 'dropped', 'reason': 'already queued via MQTT'}).encode()
                else:
                    with self.lock:
                        incident = {
                            'id': self.next_incident_id,
                            'type': incident_type,
                            'value': obj.get('value', ''),
                            'raw': obj,
                        }
                        self.next_incident_id += 1
                        self.incidents.append(incident)
                        self._position_lock[pos_key] = incident['id']
                    payload = json.dumps({'result': 'queued', 'id': incident['id'], 'type': incident['type']}).encode()
                conn.sendall(b'HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)

            elif method == 'POST' and path == '/mission_update':
                obj = json.loads(body.decode() or '{}')
                mission_id = obj.get('mission_id', '')
                unit_id = obj.get('unit_id', '')
                new_state = obj.get('state', '').upper()
                message = obj.get('message', '')
                if new_state not in {'ASSIGNED', 'BUSY', 'DONE', 'IDLE', 'ERROR'}:
                    raise ValueError('invalid state')
                with self.lock:
                    if unit_id in self.units and new_state in VEHICLE_STATES:
                        self.units[unit_id]['state'] = new_state
                    mission = self.active_missions.get(mission_id)
                    if mission:
                        mission['status'] = new_state
                        mission['updated_at'] = int(time.time())
                        self._log_mission(mission_id, unit_id, new_state, message)
                        if new_state in {'DONE', 'ERROR'}:
                            inc_type = mission.get('incident_type', '')
                            tx = mission.get('target_x', 0)
                            ty = mission.get('target_y', 0)
                            self._position_lock.pop((inc_type, tx, ty), None)
                            self.active_missions.pop(mission_id, None)
                payload = json.dumps({'result': 'updated'}).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)

            else:
                conn.sendall(b'HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n')

        except Exception:
            conn.sendall(b'HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n')
        finally:
            conn.close()

    def _render_dashboard(self):
        w = self.map['width']; h = self.map['height']
        cells = {(c['x'], c['y']): c for c in self.map['cells']}
        unit_cells = {}
        for uid, unit in self.units.items():
            x = unit.get('x'); y = unit.get('y')
            if isinstance(x, int) and isinstance(y, int):
                unit_cells[(x, y)] = (uid, unit)
        cell_size = '30px'
        infrastructure_colors = {k: '#c94c4c' for k in ('helipad', 'depot', 'harbor', 'bridge', 'charging_station')}
        infrastructure_labels = {'helipad': 'HEL', 'depot': 'DEP', 'harbor': 'HAR', 'bridge': 'BRG', 'charging_station': 'CHG'}
        live_labels = {'drone': 'DRN', 'repair_rover': 'RPR', 'supply_rover': 'SUP', 'camera': 'CAM', 'water_sensor': 'WTR'}
        role_styles = {
            'drone': {'bg': '#c084fc', 'text': '#111111', 'font': '12px'},
            'repair_rover': {'bg': '#ef4444', 'text': '#ffffff', 'font': '12px'},
            'supply_rover': {'bg': '#f59e0b', 'text': '#111111', 'font': '12px'},
            'camera': {'bg': '#60a5fa', 'text': '#000000', 'font': '12px', 'border': '2px solid #000000'},
            'water_sensor': {'bg': '#2dd4bf', 'text': '#000000', 'font': '12px', 'border': '1px solid #0f766e'},
            'supply_sensor': {'bg': '#86efac', 'text': '#000000', 'font': '12px', 'border': '1px solid #14532d'},
        }
        rows = ['<div style="margin:8px auto;font-family:Arial,sans-serif;max-width:fit-content">']
        rows.append('<div style="margin-bottom:8px;font-size:14px">Live map – data via MQTT. Refreshes every 3s.</div>')
        rows.append('<table style="border-collapse:collapse;">')
        for y in range(h):
            cols = ['<tr>']
            for x in range(w):
                c = cells.get((x, y), {'type': 'land'})
                label = c.get('infrastructure', '')
                if label:
                    bg = infrastructure_colors.get(label, '#ffb703')
                    display = infrastructure_labels.get(label, label[:3].upper())
                    text_color = '#111111'; title = label.replace('_', ' '); border_css = '1px solid #5e5e5e'; font_size = '11px'
                else:
                    terrain = c.get('type')
                    bg = '#d9c77a' if terrain == 'sand' else ('#f1e4a6' if terrain == 'sand_light' else ('#16719B' if terrain == 'water' else '#d9c77a'))
                    display = ''; text_color = '#111111' if terrain != 'water' else '#ffffff'
                    title = terrain; border_css = '1px solid #5e5e5e'; font_size = '11px'
                unit = unit_cells.get((x, y))
                if unit:
                    uid, unit_data = unit
                    role = unit_data.get('role', 'unit'); state = unit_data.get('state', 'IDLE')
                    short_name = live_labels.get(role, uid[:3].upper())
                    title = f"{title} - {uid} ({role}, {state})"
                    display = short_name
                    style = role_styles.get(role, {'bg': '#c084fc', 'text': '#111111', 'font': '12px'})
                    text_color = style.get('text', '#111111'); bg = style.get('bg', '#c084fc')
                    border_css = style.get('border', '1px solid #5e5e5e'); font_size = style.get('font', '12px')
                cols.append(f'<td title="{title}" style="width:{cell_size};min-width:{cell_size};max-width:{cell_size};height:{cell_size};min-height:{cell_size};max-height:{cell_size};padding:0;box-sizing:border-box;background:{bg};font-size:{font_size};line-height:1;font-weight:bold;color:{text_color};text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;border:{border_css}">{display}</td>')
            cols.append('</tr>'); rows.append(''.join(cols))
        rows.append('</table>')
        unit_lines = [f"{uid}: role={u.get('role')} state={u.get('state')} @ ({u.get('x','?')},{u.get('y','?')})" for uid, u in list(self.units.items())[:12]]
        history_lines = [f"#{i.get('id')} {i.get('type')} value={i.get('value')}" for i in self.history[-10:]]
        mission_lines = [f"{i.get('mission_id')} unit={i.get('unit_id','-')} state={i.get('state')} msg={i.get('message','')}" for i in self.mission_log[-12:]]
        rows.append(f'<p style="font-family:Arial,sans-serif">Units: {len(self.units)} | Incidents queued: {len(self.incidents)} | Active missions: {len(self.active_missions)}</p>')
        rows.append('<div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px;font-family:Arial,sans-serif">')
        rows.append('<div><strong>Units</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:260px;white-space:pre-wrap">' + ('\n'.join(unit_lines) or 'No units') + '</pre></div>')
        rows.append('<div><strong>Incident history</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:260px;white-space:pre-wrap">' + ('\n'.join(history_lines) or 'No incidents') + '</pre></div>')
        rows.append('<div><strong>Mission progress</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:360px;white-space:pre-wrap">' + ('\n'.join(mission_lines) or 'No missions') + '</pre></div>')
        rows.append('</div>')
        rows.append('<script>setTimeout(function(){window.location.reload();},3000);</script>')
        rows.append('</div>')
        return '\n'.join(rows)

    def serve(self, host='0.0.0.0', port=8080):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port)); s.listen(5)
        print(f'Leitstelle listening on {host}:{port}')
        while True:
            conn, addr = s.accept()
            threading.Thread(target=self.handle_connection, args=(conn, addr), daemon=True).start()


if __name__ == '__main__':
    L = Leitstelle()
    L.serve()
