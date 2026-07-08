import json, os, socket, threading, time
import paho.mqtt.client as mqtt
from rpc_utils import load_grpc_support
import dashboard as dash

# Constants declarations
MAP_FILE   = 'map.json'
MAP_STYLE  = 'island-v2'
MAP_W = MAP_H = 20
MAP_VER    = 8
RPC_TO     = 2.0
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

# MQTT / dedup / event handling settings (from origin/main)
MQTT_BROKER = os.environ.get('MQTT_BROKER', '127.0.0.1')
MQTT_PORT   = int(os.environ.get('MQTT_PORT', '1883'))
DEDUP_WIN   = 15
STALE_LIM   = 60
SKIP_TYPES  = {'water_level_ok', 'supply_level'}
ROLE_MAP    = {
    'person_detected': 'drone',
    'blocked_route': 'repair_rover',
    'structure_damage': 'repair_rover',
    'low_stock': 'supply_rover',
    'material_request': 'supply_rover',
}


# ── helpers ───────────────────────────────────────────────────────────────────
def _int(v, default=0):
    return int(v) if isinstance(v, (int, float)) else default

def _now():
    return int(time.time())


# ── main class ────────────────────────────────────────────────────────────────
class Leitstelle:
    def __init__(self):
    self.map = self._load_map()
    self.resources = RESOURCE_DEFINITIONS.copy()
    self.units = {}
        self.incidents, self.history = [], []
        self.active_missions, self.mission_log = {}, []
        self.next_incident_id = self.next_mission_id = 1
        self.lock  = threading.Lock()
        self._dedup: dict  = {}
        self._poslock: dict = {}
        self.grpc, self.pb2, self.pb2_grpc = load_grpc_support(
            os.path.dirname(os.path.abspath(__file__)))
        threading.Thread(target=self._incident_loop, daemon=True).start()
        threading.Thread(target=self._mqtt_loop,     daemon=True).start()

    # ── MQTT ─────────────────────────────────────────────────────────────────

    def _mqtt_loop(self):
        c = mqtt.Client(client_id='leitstelle-sub', clean_session=True)
        c.on_connect = lambda cl, *_: (
            cl.subscribe('sensors/events/#',     qos=1),
            cl.subscribe('vehicles/telemetry/#', qos=0),
            cl.subscribe('vehicles/missions/#',  qos=1),
            print('[mqtt] subscribed'),
        )
        c.on_message = self._on_msg
        c.reconnect_delay_set(2, 30)
        for i in range(20):
            try:
                c.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
                c.loop_forever(); return
            except Exception as e:
                print(f'[mqtt] attempt {i+1}: {e}'); time.sleep(3)

    def _on_msg(self, _c, _u, msg):
        try:
            p = json.loads(msg.payload)
        except Exception:
            return
        t = msg.topic
        if   t.startswith('sensors/events/'):     self._on_event(p)
        elif t.startswith('vehicles/telemetry/'): self._on_telemetry(p)
        elif t.startswith('vehicles/missions/'):  self._on_mission(p)

    def _on_event(self, p):
        ts  = p.get('timestamp', 0)
        if ts and (_now() - ts) > STALE_LIM:
            return
        key = (p.get('unit_id',''), p.get('type',''), p.get('x',0), p.get('y',0))
        now = time.time()
        if now - self._dedup.get(key, 0) < DEDUP_WIN:
            return
        self._dedup[key] = now
        self._dedup = {k: v for k, v in self._dedup.items() if now - v < DEDUP_WIN * 2}

        itype = p.get('type', '')
        if itype in SKIP_TYPES:
            return
        x, y  = p.get('x', 0), p.get('y', 0)
        pk    = (itype, x, y)
        with self.lock:
            if pk in self._poslock:
                return
            inc = {'id': self.next_incident_id, 'type': itype,
                   'value': p.get('value', ''), 'raw': p}
            self.next_incident_id += 1
            self.incidents.append(inc)
            self._poslock[pk] = inc['id']
        print(f'[mqtt] queued {itype} @ ({x},{y})')

    def _on_telemetry(self, p):
        uid = p.get('unit_id', '')
        if not uid: return
        with self.lock:
            u = self.units.setdefault(uid, {'id': uid,
                'role': p.get('role','vehicle'), 'state': p.get('state','IDLE')})
            u['x'] = p.get('x', u.get('x'))
            u['y'] = p.get('y', u.get('y'))
            if p.get('role'): u['role'] = p['role']
            if p.get('state','') in VEHICLE_STATES: u['state'] = p['state']

    def _on_mission(self, p):
        mid, uid = p.get('mission_id',''), p.get('unit_id','')
        state    = p.get('state','').upper()
        if state not in {'ASSIGNED','BUSY','DONE','IDLE','ERROR'}: return
        with self.lock:
            if uid in self.units and state in VEHICLE_STATES:
                self.units[uid]['state'] = state
            m = self.active_missions.get(mid)
            if m:
                m['status'] = state; m['updated_at'] = _now()
                self._log(mid, uid, state, p.get('message',''))
                if state in {'DONE','ERROR'}:
                    self._poslock.pop((m['incident_type'], m['target_x'], m['target_y']), None)
                    self.active_missions.pop(mid, None)

    # ── map ───────────────────────────────────────────────────────────────────

    def _cell_at(self, x, y):
        if not (0 <= x < MAP_W and 0 <= y < MAP_H): return {'type': 'water'}
        return self.map['cells'][y * MAP_W + x]

    def _load_map(self):
        try:
            data = json.load(open(MAP_FILE, encoding='utf-8'))
            if self._valid_map(data): return data
        except Exception: pass
        data = self._build_map()
        json.dump(data, open(MAP_FILE, 'w', encoding='utf-8'))
        return data

    def _valid_map(self, d):
        if not isinstance(d, dict): return False
        if d.get('style') != MAP_STYLE or d.get('version') != MAP_VER: return False
        if d.get('width') != MAP_W or d.get('height') != MAP_H: return False
        cells = d.get('cells', [])
        if len(cells) != MAP_W * MAP_H: return False
        by_pos = {(c['x'], c['y']): c for c in cells}
        for y in range(MAP_H):
            for x in range(MAP_W):
                c = by_pos.get((x, y))
                if not c: return False
                border = x in (0, MAP_W-1) or y in (0, MAP_H-1)
                if border and c.get('type') != 'water': return False
                if not border and c.get('type') not in {'sand','sand_light'}: return False
        return any(c.get('infrastructure') == 'harbor' for c in cells)

    def _build_map(self):
        def noise(x, y): return ((x*37 + y*19 + x*y*11) % 9) / 9.0
        cells = []
        for y in range(MAP_H):
            for x in range(MAP_W):
                if x in (0, MAP_W-1) or y in (0, MAP_H-1):
                    t = 'water'
                else:
                    s = abs(x-15)/5.8 + abs(y-5)/3.8 + noise(x,y)*0.42
                    spur = x >= 17 and 5 <= y <= 9 and (x+y)%2 == 0
                    t = 'sand' if s<=0.98 or spur else ('sand_light' if s<=1.62 else 'water')
                cells.append({'x': x, 'y': y, 'type': t})
        data = {'width':MAP_W,'height':MAP_H,'style':MAP_STYLE,'version':MAP_VER,'cells':cells}
        for (x,y), name in {(14,6):'helipad',(16,7):'bridge',(14,8):'depot',
                             (13,7):'harbor',(16,9):'charging_station'}.items():
            data['cells'][y*MAP_W+x]['infrastructure'] = name
        return data

    # ── incident pipeline ─────────────────────────────────────────────────────

    def _incident_loop(self):
        while True:
            inc = None
            with self.lock:
                if self.incidents: inc = self.incidents.pop(0)
            if inc: self._process(inc)
            time.sleep(1)

    def _process(self, inc):
        try:
            raw   = inc.get('raw', {}) if isinstance(inc.get('raw'), dict) else {}
            itype = inc.get('type', '')
            value = (inc.get('value') or
                     (f"confidence={raw['confidence']}"      if itype == 'person_detected'  and 'confidence'          in raw else '') or
                     (f"level={raw['water_level_cm']}cm"     if 'water_level' in itype      and 'water_level_cm'      in raw else '') or
                     (f"description={raw['description']}"    if itype == 'blocked_route'     and 'description'        in raw else '') or
                     (f"level={raw['supply_level_percent']}%" if itype == 'low_stock'        and 'supply_level_percent' in raw else ''))
            with self.lock:
                self.history.append({'id':inc['id'],'type':itype,'value':value,'processed_at':_now()})
            self._dispatch(inc)
        except Exception as e:
            print('process failed:', e)

    def _dispatch(self, inc):
        raw   = inc.get('raw', {}) if isinstance(inc.get('raw'), dict) else {}
        itype = inc.get('type', '')
        role  = ROLE_MAP.get(itype)
        if not role:
            x, y = raw.get('x'), raw.get('y')
            if isinstance(x, int) and isinstance(y, int):
                role = 'drone' if self._cell_at(x,y).get('type') == 'water' else None
        if not role: return

        tx, ty = _int(raw.get('x',0)), _int(raw.get('y',0))
        pri    = _int(raw.get('priority',2), 2)

        with self.lock:
            mid  = f"mission-{self.next_mission_id}"; self.next_mission_id += 1
            m = {'mission_id':mid,'incident_id':inc.get('id'),'incident_type':itype,
                 'target_x':tx,'target_y':ty,'priority':pri,'required_role':role,
                 'status':'QUEUED','assigned_unit':'','updated_at':_now()}
            self.active_missions[mid] = m
            self._log(mid, '', 'QUEUED', f'role={role}')
            uid, unit = self._pick_unit(role, tx, ty)
            if not uid:
                m['status'] = 'ERROR'; m['updated_at'] = _now()
                self._log(mid, '', 'ERROR', 'No matching IDLE unit found')
                self._poslock.pop((itype, tx, ty), None); return
            unit['state'] = 'ASSIGNED'
            m['assigned_unit'] = uid; m['status'] = 'ASSIGNED'; m['updated_at'] = _now()
            self._log(mid, uid, 'ASSIGNED', 'Dispatching via RPC')

        ok, msg = self._assign_rpc(uid, unit, m)
        with self.lock:
            cur = self.active_missions.get(mid)
            if not cur: return
            cur['status'] = 'ASSIGNED' if ok else 'ERROR'
            cur['updated_at'] = _now()
            if not ok: unit['state'] = 'ERROR'
            self._log(mid, uid, cur['status'], msg)

    def _pick_unit(self, role, tx, ty):
        for uid, u in sorted(self.units.items()):
            if u.get('role') != role: continue
            if u.get('state','IDLE') != 'IDLE': continue
            if not u.get('rpc_port'): continue
            if role != 'drone' and self._cell_at(tx,ty).get('type') == 'water': continue
            return uid, u
        return None, None

    def _assign_rpc(self, uid, unit, m):
        if not self.grpc: return False, 'gRPC unavailable'
        ch = self.grpc.insecure_channel(f"{unit.get('rpc_host') or uid}:{unit['rpc_port']}")
        try:
            reply = self.pb2_grpc.VehicleAssignmentStub(ch).AssignMission(
                self.pb2.AssignmentRequest(mission_id=m['mission_id'],
                    incident_type=m['incident_type'], target_x=m['target_x'],
                    target_y=m['target_y'], priority=m['priority']),
                timeout=RPC_TO)
            return reply.accepted, reply.message or ('accepted' if reply.accepted else 'rejected')
        except self.grpc.RpcError as e: return False, f'rpc error: {e.code().name}'
        except Exception as e:          return False, f'rpc failure: {e}'
        finally: ch.close()

    def _log(self, mid, uid, state, msg):
        self.mission_log.append({'mission_id':mid,'unit_id':uid,'state':state,
                                 'message':msg,'timestamp':_now()})
        self.mission_log = self.mission_log[-200:]

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _respond(self, conn, status, body, ctype='application/json'):
        hdr = (f'HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\n'
               f'Content-Length: {len(body)}\r\n\r\n').encode()
        conn.sendall(hdr + body)

    def handle_connection(self, conn, _addr):
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = conn.recv(1024)
            if not chunk: break
            data += chunk
        hdr, _, rest = data.partition(b'\r\n\r\n')
        lines = hdr.decode(errors='ignore').split('\r\n')
        if not lines: conn.close(); return
        method, path = lines[0].split(' ')[:2]
        hdrs = dict(l.split(':', 1) for l in lines[1:] if ':' in l)
        hdrs = {k.strip().lower(): v.strip() for k, v in hdrs.items()}
        body = rest
        if 'content-length' in hdrs:
            need = int(hdrs['content-length']) - len(body)
            while need > 0:
                c = conn.recv(1024)
                if not c: break
                body += c; need -= len(c)
        try:
<<<<<<< HEAD
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
            if   method == 'GET'  and path == '/':
                self._respond(conn, '200 OK', self._render().encode(), 'text/html; charset=utf-8')
            elif method == 'GET'  and path == '/map':
                self._respond(conn, '200 OK', json.dumps(self.map).encode())
            elif method == 'GET'  and path == '/status':
                self._respond(conn, '200 OK', json.dumps({
                    'units': self.units,
                    'incidents': self.incidents,
                    'resources': getattr(self, 'resources', []),
                    'next_incident_id': self.next_incident_id,
                    'active_missions': list(self.active_missions.values()),
                    'mission_log': self.mission_log[-50:]
                }).encode())
            elif method == 'GET'  and path == '/history':
                self._respond(conn, '200 OK', json.dumps({'history': self.history}).encode())
            elif method == 'POST' and path == '/unit':
                obj = json.loads(body or b'{}')
                uid = obj.get('id') or f'unit{len(self.units)+1}'
<<<<<<< HEAD
                role = obj.get('role', 'unit')
                if role not in ALLOWED_ROLES:
                    role = 'unit'
                obj['role'] = role
                if obj.get('state') not in VEHICLE_STATES:
                    obj['state'] = 'IDLE'
=======
                obj['role']  = obj.get('role', 'unit')
                obj['state'] = obj.get('state') if obj.get('state') in VEHICLE_STATES else 'IDLE'
>>>>>>> origin/main
                self.units[uid] = obj
                self._respond(conn, '201 Created', json.dumps({'result':'registered','id':uid}).encode())
            elif method == 'POST' and path == '/incident':
                obj   = json.loads(body or b'{}')
                itype = obj.get('type','')
                x, y  = _int(obj.get('x',0)), _int(obj.get('y',0))
                pk    = (itype, x, y)
                with self.lock:
                    if pk in self._poslock:
                        out = {'result':'dropped','reason':'already queued'}
                    else:
                        inc = {'id':self.next_incident_id,'type':itype,
                               'value':obj.get('value',''),'raw':obj}
                        self.next_incident_id += 1
                        self.incidents.append(inc)
                        self._poslock[pk] = inc['id']
                        out = {'result':'queued','id':inc['id'],'type':itype}
                self._respond(conn, '201 Created', json.dumps(out).encode())
            elif method == 'POST' and path == '/mission_update':
                obj   = json.loads(body or b'{}')
                mid   = obj.get('mission_id','')
                uid   = obj.get('unit_id','')
                state = obj.get('state','').upper()
                msg   = obj.get('message','')
                if state not in {'ASSIGNED','BUSY','DONE','IDLE','ERROR'}: raise ValueError
                with self.lock:
                    if uid in self.units and state in VEHICLE_STATES:
                        self.units[uid]['state'] = state
                    m = self.active_missions.get(mid)
                    if m:
                        m['status'] = state; m['updated_at'] = _now()
                        self._log(mid, uid, state, msg)
                        if state in {'DONE','ERROR'}:
                            self._poslock.pop((m['incident_type'],m['target_x'],m['target_y']),None)
                            self.active_missions.pop(mid, None)
                self._respond(conn, '200 OK', b'{"result":"updated"}')
            else:
                conn.sendall(b'HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n')
        except Exception:
            conn.sendall(b'HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n')
        finally:
            conn.close()

    def _render(self):
        return dash.render(self.map, self.units, self.incidents,
                           self.active_missions, self.mission_log, self.history)

    def serve(self, host='0.0.0.0', port=8080):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port)); s.listen(5)
        print(f'Leitstelle on {host}:{port}')
        while True:
            conn, addr = s.accept()
            threading.Thread(target=self.handle_connection, args=(conn, addr), daemon=True).start()


if __name__ == '__main__':
    Leitstelle().serve()
