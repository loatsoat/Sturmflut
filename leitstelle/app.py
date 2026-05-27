import json
import math
import os
import socket
import threading

MAP_FILE = 'map.json'
MAP_STYLE = 'island-v2'
MAP_WIDTH = 20
MAP_HEIGHT = 20
MAP_VERSION = 7


class Leitstelle:
    def __init__(self):
        self.map = self.load_map()
        self.units = {}
        self.incidents = []
        self.history = []
        self.next_incident_id = 1
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

        if not any(cell.get('infrastructure') == 'camera' for cell in cells):
            return False
        return True

    def create_island_map(self):
        w, h = MAP_WIDTH, MAP_HEIGHT
        cells = []

        def terrain_noise(x, y):
            # Stable pseudo-noise to keep the island pixel-like without using randomness.
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
            (15, 6): 'camera',
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
        import time
        while True:
            if self.incidents:
                inc = self.incidents.pop(0)
                print('Incident:', inc)
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
                    self.history.append({
                        'id': inc['id'],
                        'type': inc.get('type', ''),
                        'value': value,
                        'processed_at': int(time.time())
                    })
                except Exception:
                    pass
            time.sleep(1)

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
                cell_size = '30px'
                infrastructure_colors = {
                    'camera': '#c94c4c',
                    'helipad': '#c94c4c',
                    'depot': '#c94c4c',
                    'harbor': '#c94c4c',
                    'bridge': '#c94c4c',
                    'charging_station': '#c94c4c',
                }
                infrastructure_labels = {
                    'camera': 'CAM',
                    'helipad': 'HEL',
                    'depot': 'DEP',
                    'harbor': 'HAR',
                    'bridge': 'BRG',
                    'charging_station': 'CHG',
                }
                rows = ['<table style="border-collapse:collapse;margin:8px auto;font-family:Arial,sans-serif">']
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
                        cols.append(
                            f'<td title="{title}" '
                            f'style="width:{cell_size};min-width:{cell_size};max-width:{cell_size};'
                            f'height:{cell_size};min-height:{cell_size};max-height:{cell_size};'
                            f'padding:0;border:1px solid #5e5e5e;box-sizing:border-box;'
                            f'background:{bg};font-size:9px;line-height:1;font-weight:bold;'
                            f'color:{text_color};text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap">{display}</td>'
                        )
                    cols.append('</tr>'); rows.append(''.join(cols))
                rows.append('</table>')
                rows.append('<div style="width:fit-content;margin:8px auto;font-family:Arial,sans-serif;font-size:14px">')
                rows.append('<strong>Legend:</strong> sand gold, sand light cream, all infrastructure red')
                rows.append(f'<p>Units: {len(self.units)} Incidents: {len(self.incidents)}</p>')
                unit_lines = [f"{uid}: {unit.get('role', 'unit')} @ ({unit.get('x', '?')},{unit.get('y', '?')})" for uid, unit in list(self.units.items())[:10]]
                history_lines = [f"#{item.get('id')} {item.get('type', '')} value={item.get('value', '')}" for item in self.history[-10:]]
                rows.append('<div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px">')
                rows.append('<div><strong>Units log</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:260px;white-space:pre-wrap">' + ('\n'.join(unit_lines) if unit_lines else 'No units registered yet') + '</pre></div>')
                rows.append('<div><strong>Incident history</strong><pre style="margin:4px 0 0 0;padding:8px;background:#f6f6f6;border:1px solid #ddd;min-width:260px;white-space:pre-wrap">' + ('\n'.join(history_lines) if history_lines else 'No incidents processed yet') + '</pre></div>')
                rows.append('</div>')
                rows.append('</div>')
                payload = ('\n'.join(rows)).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            elif method == 'GET' and path == '/status':
                payload = json.dumps({'units': self.units, 'incidents': self.incidents, 'next_incident_id': self.next_incident_id}).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            elif method == 'GET' and path == '/history':
                payload = json.dumps({'history': self.history}).encode()
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
            elif method == 'POST' and path == '/unit':
                obj = json.loads(body.decode() or '{}')
                uid = obj.get('id') or f'unit{len(self.units)+1}'
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
