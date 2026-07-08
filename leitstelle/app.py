import json
import math
import os
import socket
import threading
import time

from rpc_utils import load_grpc_support

MAP_FILE = 'map.json'
MAP_STYLE = 'island-v2'
MAP_WIDTH = 20
MAP_HEIGHT = 20
MAP_VERSION = 8
RPC_TIMEOUT_SECONDS = 2.0

VEHICLE_STATES = {'IDLE', 'ASSIGNED', 'BUSY', 'ERROR'}
ALLOWED_ROLES = {
    'drone', 'repair_rover', 'supply_rover',
    'camera', 'water_sensor', 'supply_sensor',
}
RESOURCE_DEFINITIONS = [
    {
        'id': 'charging_station',
        'name': 'Charging Station',
        'type': 'charging_station',
        'x': 16,
        'y': 9,
        'capacity': 1,
        'description': 'Central battery recharge point for drones and rovers',
    }
]
RESOURCE_USER_ROLES = {
    'charging_station': ['drone', 'repair_rover', 'supply_rover'],
}


class Leitstelle:
    def __init__(self):
        self.map = self.load_map()
        self.resources = RESOURCE_DEFINITIONS.copy()
        self.units = {}
        self.incidents = []
        self.history = []
        self.active_missions = {}
        self.mission_log = []
        self.next_incident_id = 1
        self.next_mission_id = 1
        self.lock = threading.Lock()
        self.grpc, self.assignment_pb2, self.assignment_pb2_grpc = load_grpc_support(
            os.path.dirname(os.path.abspath(__file__))
        )
        threading.Thread(target=self.incident_processor, daemon=True).start()

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
                elif inc.get('type') == 'water_level_alert' and 'value' in raw:
                    value = f"level={raw.get('value')}"
                elif inc.get('type') == 'blocked_route' and raw.get('description'):
                    value = f"description={raw.get('description')}"

            with self.lock:
                self.history.append({
                    'id': inc['id'],
                    'type': inc.get('type', ''),
                    'value': value,
                    'processed_at': int(time.time())
                })

            self._dispatch_incident(inc)
        except Exception as exc:
            print('process incident failed:', exc)

    def _determine_role(self, incident_type, raw):
        # Person detection or hard-to-reach locations use the drone
        if incident_type == 'person_detected':
            return 'drone'

        # Structure or blocked-route events use the repair rover
        if incident_type in {'blocked_route', 'structure_damage'}:
            return 'repair_rover'

        # Low stock or material requests use the supply rover
        if incident_type in {'low_stock', 'material_request'}:
            return 'supply_rover'

        # Fallback: if coordinates point to water or otherwise hard-to-reach, prefer drone
        x = raw.get('x')
        y = raw.get('y')
        if isinstance(x, int) and isinstance(y, int):
            cell = self._cell_at(x, y)
            if cell.get('type') == 'water':
                return 'drone'
        return None

    def _cell_at(self, x, y):
        if x < 0 or y < 0 or x >= self.map['width'] or y >= self.map['height']:
            return {'type': 'water'}
        idx = y * self.map['width'] + x
        return self.map['cells'][idx]

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
            elif method == 'GET' and path == '/':
                w = self.map['width']; h = self.map['height']
                cells = {(c['x'], c['y']): c for c in self.map['cells']}
                unit_cells = {}
                for uid, unit in self.units.items():
                    x = unit.get('x')
                    y = unit.get('y')
                    if isinstance(x, int) and isinstance(y, int):
                        unit_cells[(x, y)] = (uid, unit)
                cell_size = '30px'
                infrastructure_colors = {
                    'helipad': '#c94c4c',
                    'depot': '#c94c4c',
                    'harbor': '#c94c4c',
                    'bridge': '#c94c4c',
                    'charging_station': '#c94c4c',
                }
                infrastructure_labels = {
                    'helipad': 'HEL',
                    'depot': 'DEP',
                    'harbor': 'HAR',
                    'bridge': 'BRG',
                    'charging_station': 'CHG',
                }
                rows = ['<div style="margin:8px auto;font-family:Arial,sans-serif;max-width:fit-content">']
                rows.append('<div style="margin-bottom:8px;font-size:14px">Live map refreshes every 3 seconds. Purple labels show current unit and sensor positions.</div>')
                rows.append('<table style="border-collapse:collapse;">')
                live_labels = {
                    'drone': 'DRN',
                    'repair_rover': 'RPR',
                    'supply_rover': 'SUP',
                    'camera': 'CAM',
                    'water_sensor': 'WTR',
                }
                # role specific styles to make sensors/camera more visible
                role_styles = {
                    'drone': {'bg': '#c084fc', 'text': '#111111', 'font': '12px'},
                    'repair_rover': {'bg': '#ef4444', 'text': '#ffffff', 'font': '12px'},
                    'supply_rover': {'bg': '#f59e0b', 'text': '#111111', 'font': '12px'},
                    'camera': {'bg': '#60a5fa', 'text': '#000000', 'font': '12px', 'border': '2px solid #000000'},
                    'water_sensor': {'bg': '#2dd4bf', 'text': '#000000', 'font': '12px', 'border': '1px solid #0f766e'},
                    'supply_sensor': {'bg': '#86efac', 'text': '#000000', 'font': '12px', 'border': '1px solid #14532d'},
                }
                for y in range(h):
                    cols = ['<tr>']
                    for x in range(w):
                        c = cells.get((x, y), {'type': 'land'})
                        label = c.get('infrastructure', '')
                        if label:
                            bg = infrastructure_colors.get(label, '#ffb703')
                            display = infrastructure_labels.get(label, label[:3].upper())
                            text_color = '#111111'
                            title = label.replace('_', ' ')
                        else:
                            terrain = c.get('type')
                            if terrain == 'sand':
                                bg = '#d9c77a'
                            elif terrain == 'sand_light':
                                bg = '#f1e4a6'
                            else:
                                bg = '#16719B' if terrain == 'water' else '#d9c77a'
                            display = ''
                            text_color = '#111111' if terrain != 'water' else '#ffffff'
                            title = terrain
                        border_css = '1px solid #5e5e5e'
                        font_size = '11px'
                        unit = unit_cells.get((x, y))
                        if unit:
                            uid, unit_data = unit
                            role = unit_data.get('role', 'unit')
                            state = unit_data.get('state', 'IDLE')
                            short_name = live_labels.get(role, uid[:3].upper())
                            title = f"{title} - {uid} ({role}, {state})"
                            display = short_name
                            style = role_styles.get(role, {'bg': '#c084fc', 'text': '#111111', 'font': '12px'})
                            text_color = style.get('text', '#111111')
                            bg = style.get('bg', '#c084fc')
                            border_css = style.get('border', '1px solid #5e5e5e')
                            font_size = style.get('font', '12px')
                        cols.append(
                            f'<td title="{title}" '
                            f'style="width:{cell_size};min-width:{cell_size};max-width:{cell_size};'
                            f'height:{cell_size};min-height:{cell_size};max-height:{cell_size};'
                            f'padding:0;box-sizing:border-box;'
                            f'background:{bg};font-size:{font_size};line-height:1;font-weight:bold;'
                            f'color:{text_color};text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;border:{border_css}">{display}</td>'
                        )
                    cols.append('</tr>'); rows.append(''.join(cols))
                rows.append('</table>')
                rows.append('<div style="width:fit-content;margin:8px auto;font-family:Arial,sans-serif;font-size:14px">')
                rows.append('<strong>Legend:</strong> sand gold, sand light cream')
                rows.append('<div style="display:flex;gap:12px;margin-top:6px;align-items:center">')
                rows.append('<div style="display:flex;gap:6px;align-items:center"><div style="width:16px;height:16px;background:#60a5fa;border:1px solid #000"></div><div>CAM</div></div>')
                rows.append('<div style="display:flex;gap:6px;align-items:center"><div style="width:16px;height:16px;background:#2dd4bf;border:1px solid #0f766e"></div><div>WTR</div></div>')
                rows.append('<div style="display:flex;gap:6px;align-items:center"><div style="width:16px;height:16px;background:#86efac;border:1px solid #14532d"></div><div>SUP_SENSOR</div></div>')
                rows.append('<div style="display:flex;gap:6px;align-items:center"><div style="width:16px;height:16px;background:#c084fc;border:1px solid #5e5e5e"></div><div>DRN</div></div>')
                rows.append('<div style="display:flex;gap:6px;align-items:center"><div style="width:16px;height:16px;background:#c94c4c;border:1px solid #7f1d1d"></div><div>CHG</div></div>')
                rows.append('</div>')
                rows.append(f'<p>Units: {len(self.units)} Incidents queue: {len(self.incidents)} Active missions: {len(self.active_missions)} Resources: {len(self.resources)}</p>')
                unit_lines = [
                    f"{uid}: role={unit.get('role', 'unit')} state={unit.get('state', 'IDLE')} @ ({unit.get('x', '?')},{unit.get('y', '?')}) rpc={unit.get('rpc_host', '?')}:{unit.get('rpc_port', '?')}"
                    for uid, unit in list(self.units.items())[:12]
                ]
                history_lines = [f"#{item.get('id')} {item.get('type', '')} value={item.get('value', '')}" for item in self.history[-10:]]
                mission_lines = [
                    f"{item.get('mission_id')} unit={item.get('unit_id', '-')} state={item.get('state')} msg={item.get('message', '')}"
                    for item in self.mission_log[-12:]
                ]
                rows.append('<div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px">')
                rows.append('<div><strong>Units log</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:260px;white-space:pre-wrap">' + ('\n'.join(unit_lines) if unit_lines else 'No units registered yet') + '</pre></div>')
                rows.append('<div><strong>Incident history</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:260px;white-space:pre-wrap">' + ('\n'.join(history_lines) if history_lines else 'No incidents processed yet') + '</pre></div>')
                rows.append('<div><strong>Mission progress</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:360px;white-space:pre-wrap">' + ('\n'.join(mission_lines) if mission_lines else 'No mission events yet') + '</pre></div>')
                rows.append('</div>')
                rows.append('<script>setTimeout(function(){window.location.reload();}, 3000);</script>')
                rows.append('</div>')
                payload = ('\n'.join(rows)).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            elif method == 'GET' and path == '/status':
                payload = json.dumps({
                    'units': self.units,
                    'incidents': self.incidents,
                    'resources': self.resources,
                    'next_incident_id': self.next_incident_id,
                    'active_missions': list(self.active_missions.values()),
                    'mission_log': self.mission_log[-50:],
                }).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            elif method == 'GET' and path == '/history':
                payload = json.dumps({'history': self.history}).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            elif method == 'POST' and path == '/unit':
                obj = json.loads(body.decode() or '{}')
                uid = obj.get('id') or f'unit{len(self.units)+1}'
                role = obj.get('role', 'unit')
                if role not in ALLOWED_ROLES:
                    role = 'unit'
                obj['role'] = role
                if obj.get('state') not in VEHICLE_STATES:
                    obj['state'] = 'IDLE'
                self.units[uid] = obj
                payload = json.dumps({'result': 'registered', 'id': uid}).encode()
                conn.sendall(b'HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            elif method == 'POST' and path == '/incident':
                obj = json.loads(body.decode() or '{}')
                incident = {
                    'id': self.next_incident_id,
                    'type': obj.get('type', ''),
                    'value': obj.get('value', ''),
                    'raw': obj,
                }
                self.next_incident_id += 1
                self.incidents.append(incident)
                payload = json.dumps({'result': 'queued', 'id': incident['id'], 'type': incident['type'], 'value': incident['value']}).encode()
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
                            self.active_missions.pop(mission_id, None)
                payload = json.dumps({'result': 'updated'}).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            else:
                conn.sendall(b'HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n')
        except Exception:
            conn.sendall(b'HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n')
        finally:
            conn.close()

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
