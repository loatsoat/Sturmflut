import socket, threading, json, os

MAP_FILE = 'map.json'


class Leitstelle:
    def __init__(self):
        self.map = self.load_map()
        self.units = {}
        self.incidents = []
        self.history = []
        self.next_incident_id = 1
        threading.Thread(target=self.incident_processor, daemon=True).start()

    def load_map(self):
        # ensure 20x20 map
        try:
            data = json.load(open(MAP_FILE))
            if len(data.get('cells', [])) >= 400:
                return data
        except Exception:
            pass
        w, h = 20, 20
        cells = []
        for y in range(h):
            for x in range(w):
                t = 'water' if (x + y) % 7 == 0 else 'land'
                cells.append({'x': x, 'y': y, 'type': t})
        data = {'width': w, 'height': h, 'cells': cells}
        # add a few infrastructures
        infra = {(2, 2): 'depot', (10, 0): 'bridge', (5, 15): 'charging_station', (18, 4): 'helipad'}
        for (x, y), name in infra.items():
            idx = y * w + x
            if 0 <= idx < len(data['cells']):
                data['cells'][idx]['infrastructure'] = name
        json.dump(data, open(MAP_FILE, 'w'))
        return data

    def incident_processor(self):
        import time
        while True:
            if self.incidents:
                inc = self.incidents.pop(0)
                print('Incident:', inc)
                try:
                    self.history.append({
                        'id': inc['id'],
                        'type': inc.get('type', ''),
                        'value': inc.get('value', ''),
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
                rows = ['<table style="border-collapse:collapse">']
                for y in range(h):
                    cols = ['<tr>']
                    for x in range(w):
                        c = cells.get((x, y), {'type': 'land'})
                        bg = '#89CFF0' if c.get('type') == 'water' else '#C2B280'
                        label = c.get('infrastructure', '')
                        cols.append(f'<td style="width:20px;height:18px;border:1px solid #666;background:{bg};font-size:8px;text-align:center">{label}</td>')
                    cols.append('</tr>'); rows.append(''.join(cols))
                rows.append('</table>')
                rows.append(f'<p>Units: {len(self.units)} Incidents: {len(self.incidents)}</p>')
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
