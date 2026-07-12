import json
import os
import threading
import time

from mqtt_utils import publish_coordination


class RicartAgrawalaCoordinator:
    """Simple MQTT-based Ricart/Agrawala coordinator for a shared resource."""

    def __init__(self, node_id, mqtt_client, resource_id='charging_station', peers=None):
        self.node_id = node_id
        self.resource_id = resource_id
        self.mqtt_client = mqtt_client
        self.peers = [p.strip() for p in (peers or []) if p and p.strip()]
        self.peers = [p for p in self.peers if p != node_id]
        self.lock = threading.RLock()
        self.state = 'IDLE'
        self.logical_clock = 0
        self.current_request = None
        self.reply_from = set()
        self.deferred_requests = []
        self._wait_event = threading.Event()
        self._last_owner = None

    def start(self):
        self.mqtt_client.subscribe('vehicles/coordination/#', qos=1)
        self.mqtt_client.on_message = self._on_message

    @property
    def is_held(self):
        return self.state == 'HELD'

    def request_access(self, resource_id='charging_station', hold_seconds=2.0, timeout=6.0):
        with self.lock:
            if self.state == 'HELD':
                return True
            self.resource_id = resource_id
            self.logical_clock += 1
            self.state = 'WAITING'
            self.current_request = {
                'type': 'request',
                'resource_id': self.resource_id,
                'from_node': self.node_id,
                'timestamp': self.logical_clock,
            }
            self.reply_from = set()
            self._wait_event.clear()
            self._publish_state('WAITING')
            publish_coordination(self.mqtt_client, self.resource_id, 'requests', self.current_request)

        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if self.reply_count() >= len(self.peers):
                    self.state = 'HELD'
                    self._publish_state('HELD')
                    return True
            self._wait_event.wait(0.2)

        with self.lock:
            if self.reply_count() >= len(self.peers):
                self.state = 'HELD'
                self._publish_state('HELD')
                return True
            self.state = 'IDLE'
            self.current_request = None
            self._publish_state('IDLE')
            return False

    def release_access(self):
        with self.lock:
            if self.state != 'HELD':
                return
            self.state = 'IDLE'
            self._last_owner = None
            self.current_request = None
            self.reply_from = set()
            self._wait_event.clear()
            self._publish_state('IDLE')
            publish_coordination(self.mqtt_client, self.resource_id, 'releases', {
                'type': 'release',
                'resource_id': self.resource_id,
                'from_node': self.node_id,
                'timestamp': self.logical_clock,
            })
            while self.deferred_requests:
                req = self.deferred_requests.pop(0)
                self._send_reply(req)

    def _on_message(self, _client, _userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        topic = msg.topic
        if topic.startswith('vehicles/coordination/requests/'):
            self._handle_request(payload)
        elif topic.startswith('vehicles/coordination/replies/'):
            self._handle_reply(payload)
        elif topic.startswith('vehicles/coordination/releases/'):
            self._handle_release(payload)

    def _handle_request(self, payload):
        if payload.get('resource_id') != self.resource_id:
            return
        if payload.get('from_node') == self.node_id:
            return
        with self.lock:
            self.logical_clock = max(self.logical_clock, int(payload.get('timestamp', 0))) + 1
            if self.state == 'HELD' or (self.state == 'WAITING' and self._incoming_has_priority(payload)):
                self.deferred_requests.append(payload)
                self._publish_state('WAITING')
                return
            self._send_reply(payload)

    def _handle_reply(self, payload):
        if payload.get('resource_id') != self.resource_id:
            return
        if payload.get('to_node') != self.node_id:
            return
        if payload.get('from_node') == self.node_id:
            return
        with self.lock:
            if payload.get('from_node') in self.reply_from:
                return
            self.reply_from.add(payload.get('from_node'))
            if self.state == 'WAITING' and self.reply_count() >= len(self.peers):
                self.state = 'HELD'
                self._last_owner = self.node_id
                self._publish_state('HELD')
                self._wait_event.set()

    def _handle_release(self, payload):
        if payload.get('resource_id') != self.resource_id:
            return
        if payload.get('from_node') == self.node_id:
            return
        with self.lock:
            self.logical_clock = max(self.logical_clock, int(payload.get('timestamp', 0))) + 1
            self._publish_state('IDLE')
            while self.deferred_requests:
                req = self.deferred_requests.pop(0)
                self._send_reply(req)

    def _send_reply(self, request):
        if request.get('from_node') == self.node_id:
            return
        payload = {
            'type': 'reply',
            'resource_id': self.resource_id,
            'from_node': self.node_id,
            'to_node': request.get('from_node'),
            'timestamp': self.logical_clock,
        }
        publish_coordination(self.mqtt_client, self.resource_id, 'replies', payload)

    def _publish_state(self, state):
        payload = {
            'type': 'state',
            'resource_id': self.resource_id,
            'state': state,
            'owner': self.node_id if state == 'HELD' else None,
            'logical_time': self.logical_clock,
            'node_id': self.node_id,
        }
        publish_coordination(self.mqtt_client, self.resource_id, 'state', payload)

    def _incoming_has_priority(self, payload):
        if self.current_request is None:
            return False
        incoming_ts = int(payload.get('timestamp', 0))
        my_ts = int(self.current_request.get('timestamp', 0))
        if incoming_ts < my_ts:
            return False
        if incoming_ts > my_ts:
            return True
        return payload.get('from_node', '') > self.current_request.get('from_node', '')

    def reply_count(self):
        return len(self.reply_from)
