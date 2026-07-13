"""Ricart/Agrawala distributed mutual exclusion over MQTT."""

import json
import os
import threading
import time

from mqtt_utils import build_client, publish_coordination

ALL_VEHICLE_PEERS = ['drone-1', 'repair-rover-1', 'supply-rover-1']


class RicartAgrawalaCoordinator:

    def __init__(self, node_id, pub_client, resource_id='charging_station', peers=None):
        self.node_id       = node_id
        self.resource_id   = resource_id
        self._pub          = pub_client
        self._sub          = None
        raw_peers = peers if peers is not None else ALL_VEHICLE_PEERS
        self.peers = [p for p in raw_peers if p and p.strip() and p != node_id]
        self._lock         = threading.RLock()
        self.state         = 'IDLE'
        self.logical_clock = 0
        self._req          = None
        self._replies      = set()
        self._deferred     = []
        self._ready        = threading.Event()

    def start(self, sub_client=None):
        """Create dedicated subscriber and subscribe to coordination topics.

        In production (Docker), sub_client is None and a real paho MQTT client
        is created via build_client().  In tests, pass a SimMqttClient so the
        harness can deliver messages without a real broker.
        """
        if sub_client is not None:
            self._sub = sub_client
        else:
            self._sub = build_client(f'{self.node_id}-coord-sub')
        self._sub.on_message = self._on_message
        self._sub.subscribe('vehicles/coordination/#', qos=1)
        print(f'[coord:{self.node_id}] started, peers={self.peers}')

    def request_access(self, resource_id='charging_station', timeout=30.0):
        """Block until this node holds the resource, or timeout expires.
        Returns True if HELD, False on timeout.
        """
        with self._lock:
            if self.state == 'HELD':
                return True
            self.resource_id = resource_id
            self.logical_clock += 1
            self.state  = 'WAITING'
            self._req   = {
                'type':        'request',
                'resource_id': resource_id,
                'from_node':   self.node_id,
                'timestamp':   self.logical_clock,
            }
            self._replies.clear()
            self._ready.clear()
            self._publish_state('WAITING')
            publish_coordination(self._pub, resource_id, 'requests', self._req)
            print(f'[coord:{self.node_id}] REQUEST sent  clock={self.logical_clock}')

        if not self.peers:
            with self._lock:
                self.state = 'HELD'
                self._publish_state('HELD')
                print(f'[coord:{self.node_id}] HELD (no peers)')
            return True

        deadline = time.time() + timeout
        while time.time() < deadline:
            self._ready.wait(timeout=min(0.5, deadline - time.time()))
            with self._lock:
                if self.state == 'HELD':
                    print(f'[coord:{self.node_id}] ENTER charging_station  clock={self.logical_clock}')
                    return True

        with self._lock:
            print(f'[coord:{self.node_id}] TIMEOUT waiting for replies '
                  f'({len(self._replies)}/{len(self.peers)} received)')
            self.state = 'IDLE'
            self._req  = None
            self._publish_state('IDLE')
            deferred, self._deferred = list(self._deferred), []

        for req in deferred:
            self._send_reply(req)
        return False

    def release_access(self):
        """Release the resource and send deferred replies."""
        with self._lock:
            if self.state != 'HELD':
                return
            self.state = 'IDLE'
            self._req  = None
            self._ready.clear()
            self._publish_state('IDLE')
            publish_coordination(self._pub, self.resource_id, 'releases', {
                'type':        'release',
                'resource_id': self.resource_id,
                'from_node':   self.node_id,
                'timestamp':   self.logical_clock,
            })
            print(f'[coord:{self.node_id}] EXIT  charging_station  clock={self.logical_clock}')
            deferred, self._deferred = list(self._deferred), []

        for req in deferred:
            self._send_reply(req)

    def _on_message(self, _client, _userdata, msg):
        try:
            p = json.loads(msg.payload.decode('utf-8'))
        except Exception:
            return
        if not isinstance(p, dict):
            return
        t = msg.topic
        if   t.startswith('vehicles/coordination/requests/'): self._handle_request(p)
        elif t.startswith('vehicles/coordination/replies/'):  self._handle_reply(p)
        elif t.startswith('vehicles/coordination/releases/'): self._handle_release(p)

    def _handle_request(self, p):
        if p.get('resource_id') != self.resource_id: return
        if p.get('from_node')   == self.node_id:     return
        with self._lock:
            self.logical_clock = max(self.logical_clock, int(p.get('timestamp', 0))) + 1
            if self.state == 'HELD' or (self.state == 'WAITING' and self._i_have_priority(p)):
                self._deferred.append(p)
                print(f'[coord:{self.node_id}] DEFERRED request from {p.get("from_node")}')
            else:
                self._send_reply(p)

    def _handle_reply(self, p):
        if p.get('resource_id') != self.resource_id: return
        if p.get('to_node')     != self.node_id:     return
        if p.get('from_node')   == self.node_id:     return
        with self._lock:
            self.logical_clock = max(self.logical_clock, int(p.get('timestamp', 0))) + 1
            sender = p.get('from_node')
            if sender in self._replies:
                return
            self._replies.add(sender)
            print(f'[coord:{self.node_id}] REPLY from {sender}  '
                  f'({len(self._replies)}/{len(self.peers)})')
            if self.state == 'WAITING' and len(self._replies) >= len(self.peers):
                self.state = 'HELD'
                self._publish_state('HELD')
                self._ready.set()

    def _handle_release(self, p):
        """Handle RELEASE messages from peers."""
        if p.get('resource_id') != self.resource_id: return
        if p.get('from_node')   == self.node_id:     return
        with self._lock:
            self.logical_clock = max(self.logical_clock, int(p.get('timestamp', 0))) + 1

    def _i_have_priority(self, incoming):
        """Return True if our request has higher priority than incoming."""
        if self._req is None:
            return False
        my_ts = int(self._req.get('timestamp', 0))
        in_ts = int(incoming.get('timestamp', 0))
        if my_ts != in_ts:
            return my_ts < in_ts
        return self.node_id < incoming.get('from_node', '')

    def _send_reply(self, req):
        if req.get('from_node') == self.node_id:
            return
        with self._lock:
            self.logical_clock += 1
            ts = self.logical_clock
        publish_coordination(self._pub, self.resource_id, 'replies', {
            'type':        'reply',
            'resource_id': self.resource_id,
            'from_node':   self.node_id,
            'to_node':     req.get('from_node'),
            'timestamp':   ts,
        })
        print(f'[coord:{self.node_id}] REPLY sent to {req.get("from_node")}  clock={ts}')

    def _publish_state(self, state):
        """Publish observer state update for the dashboard feed."""
        publish_coordination(self._pub, self.resource_id, 'state', {
            'type':         'state',
            'resource_id':  self.resource_id,
            'state':        state,
            'owner':        self.node_id if state == 'HELD' else None,
            'logical_time': self.logical_clock,
            'node_id':      self.node_id,
        })
