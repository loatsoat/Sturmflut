import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sensoren'))

from communication_router import CommunicationRouter


class DummyClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length)
        payload = json.loads(body.decode('utf-8'))
        assert payload['unit_id'] == 'x'
        self.send_response(200)
        self.end_headers()

    def log_message(self, _format, *args):
        return


def run_http_server():
    server = HTTPServer(('127.0.0.1', 18080), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_mqtt_preferred_when_available():
    router = CommunicationRouter(mqtt_client=DummyClient(), http_url='http://127.0.0.1:18080')
    delivered = router.send('telemetry', {'unit_id': 'x'}, prefer='mqtt')
    assert delivered['channel'] == 'mqtt'
    assert router.last_error is None


def test_http_fallback_when_mqtt_unavailable():
    class FailingClient:
        def publish(self, *args, **kwargs):
            raise RuntimeError('broker down')

    server, _ = run_http_server()
    router = CommunicationRouter(mqtt_client=FailingClient(), http_url='http://127.0.0.1:18080')
    delivered = router.send('mission', {'unit_id': 'x'}, prefer='mqtt')
    server.shutdown()
    assert delivered['channel'] == 'http'
    assert delivered['ok'] is True


def test_selects_http_for_large_payloads():
    server, _ = run_http_server()
    router = CommunicationRouter(mqtt_client=DummyClient(), http_url='http://127.0.0.1:18080')
    big_payload = {'unit_id': 'x', 'data': 'a' * 20000}
    delivered = router.send('mission', big_payload, prefer='auto')
    server.shutdown()
    assert delivered['channel'] == 'http'
