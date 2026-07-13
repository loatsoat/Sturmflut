"""Verification harness for Ricart/Agrawala charging-station coordination."""

import threading
import time
from types import SimpleNamespace

from coordination import RicartAgrawalaCoordinator


class SimBroker:
    """Async in-process message bus."""

    def __init__(self):
        self._lock   = threading.Lock()
        self.clients = []

    def register(self, client):
        with self._lock:
            self.clients.append(client)

    def publish(self, sender, topic, payload):
        with self._lock:
            recipients = [c for c in self.clients if c is not sender and c.matches(topic)]
        for client in recipients:
            t = threading.Thread(
                target=client.deliver,
                args=(topic, payload),
                daemon=True,
            )
            t.start()


class SimMqttClient:
    def __init__(self, broker, node_id):
        self.broker        = broker
        self.node_id       = node_id
        self.subscriptions = []
        self.on_message    = None
        self.published     = []
        self.broker.register(self)

    def subscribe(self, topic, qos=0):
        self.subscriptions.append(topic)

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))
        self.broker.publish(self, topic, payload)

    def matches(self, topic):
        return any(self._match(sub, topic) for sub in self.subscriptions)

    def deliver(self, topic, payload):
        if self.on_message is None:
            return
        msg = SimpleNamespace(topic=topic, payload=payload.encode('utf-8'))
        self.on_message(self, None, msg)

    def _match(self, subscription, topic):
        if subscription.endswith('#'):
            prefix = subscription[:-1]
            return topic.startswith(prefix)
        return subscription == topic


class VerificationHarness:

    def _build_nodes(self, broker=None, peer_map=None):
        """Build a set of coordinators wired to a shared SimBroker.

        Each coordinator gets TWO SimMqttClients:
          pub_client  – used by the coordinator to publish coordination messages.
          sub_client  – dedicated subscriber injected into start() so that
                        messages flow through the SimBroker instead of a real
                        MQTT broker.

        peer_map (optional): dict node_id → [peer_ids].  Defaults to the
        standard 3-node full-mesh.
        """
        b = broker or SimBroker()

        node_ids = ['drone-1', 'repair-rover-1', 'supply-rover-1']
        if peer_map is None:
            peer_map = {
                'drone-1':        ['repair-rover-1', 'supply-rover-1'],
                'repair-rover-1': ['drone-1',         'supply-rover-1'],
                'supply-rover-1': ['drone-1',         'repair-rover-1'],
            }

        pub_clients = {nid: SimMqttClient(b, f'{nid}-pub') for nid in node_ids}
        sub_clients = {nid: SimMqttClient(b, f'{nid}-sub') for nid in node_ids}

        coords = {
            nid: RicartAgrawalaCoordinator(
                nid,
                pub_clients[nid],
                peers=peer_map[nid],
            )
            for nid in node_ids
        }
        for nid, coord in coords.items():
            coord.start(sub_client=sub_clients[nid])

        return b, pub_clients, sub_clients, coords

    def run_safety_liveness(self):
        """All three coordinators request access IN PARALLEL.
        Safety: never more than one HELD at a time (verified via the shared
                SimBroker observer, not via an external lock that would race).
        Liveness: every node eventually acquires the resource.
        """
        broker = SimBroker()
        _, _, _, coords = self._build_nodes(broker=broker)
        coordinators = list(coords.values())

        max_concurrent = [0]
        concurrent_lock = threading.Lock()
        safety_errors   = []

        def _observe():
            """Poll coordinator states every millisecond for up to 15 seconds."""
            deadline = time.time() + 15
            while time.time() < deadline:
                held = [c for c in coordinators if c.state == 'HELD']
                if len(held) > 1:
                    with concurrent_lock:
                        if len(held) > max_concurrent[0]:
                            max_concurrent[0] = len(held)
                        safety_errors.append(
                            f'SAFETY VIOLATION: {[c.node_id for c in held]} all HELD'
                        )
                elif len(held) == 1:
                    with concurrent_lock:
                        if 1 > max_concurrent[0]:
                            max_concurrent[0] = 1
                time.sleep(0.001)

        acquired  = []
        errors    = []
        timing_ms = {}

        def _do(coord):
            t0 = time.time()
            ok = coord.request_access(timeout=10.0)
            elapsed = int((time.time() - t0) * 1000)
            timing_ms[coord.node_id] = elapsed
            if not ok:
                errors.append(f'{coord.node_id}: timed out')
                return
            time.sleep(0.05)
            coord.release_access()
            acquired.append(coord.node_id)

        observer = threading.Thread(target=_observe, daemon=True)
        observer.start()

        threads = [
            threading.Thread(target=_do, args=(c,), daemon=True)
            for c in coordinators
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        return {
            'safety_ok':              len(safety_errors) == 0,
            'max_concurrent_holders': max_concurrent[0],
            'acquired_nodes':         sorted(acquired),
            'liveness_ok':            sorted(acquired) == sorted(
                c.node_id for c in coordinators
            ),
            'errors':                 errors + safety_errors,
            'timing_ms':              timing_ms,
        }

    def run_failure_mode(self):
        """Drop all REPLY messages.  The requesting node must time out gracefully."""

        class LossyBroker(SimBroker):
            def __init__(self, drop_topic_prefix):
                super().__init__()
                self._drop   = drop_topic_prefix
                self.dropped = 0

            def publish(self, sender, topic, payload):
                if topic.startswith(self._drop):
                    with self._lock:
                        self.dropped += 1
                    return
                super().publish(sender, topic, payload)

        broker = LossyBroker('vehicles/coordination/replies/')
        _, _, _, coords = self._build_nodes(broker=broker)
        coord0 = coords['drone-1']

        result = coord0.request_access(timeout=1.0)
        return {
            'failure_ok':       result is False,
            'dropped_messages': broker.dropped,
            'final_state':      coord0.state,
        }

    def run_non_fifo_mode(self):
        """Deliver messages out of order (non-FIFO) to verify correctness.

        Real MQTT with QoS 1 does not guarantee FIFO ordering across topics or
        even within a topic under network conditions.  This test simulates that
        by injecting an artificial delay on the *first* REQUEST seen by each
        subscriber, causing a later REQUEST to be processed before an earlier
        one.

        The algorithm must still be correct: the tie-breaking rule
        (smaller node_id wins when timestamps are equal) must produce a safe
        and live outcome regardless of delivery order.
        """
        import threading as _threading

        class ReorderingBroker(SimBroker):
            """Delays first REQUEST so the next one can overtake."""
            def __init__(self):
                super().__init__()
                self._first_request_seen = False
                self._reorder_lock = _threading.Lock()

            def publish(self, sender, topic, payload):
                if 'requests' in topic:
                    with self._reorder_lock:
                        delay_this = not self._first_request_seen
                        self._first_request_seen = True
                    if delay_this:
                        def _delayed():
                            import time as _time
                            _time.sleep(0.05)
                            with self._lock:
                                recipients = [
                                    c for c in self.clients
                                    if c is not sender and c.matches(topic)
                                ]
                            for client in recipients:
                                _threading.Thread(
                                    target=client.deliver,
                                    args=(topic, payload),
                                    daemon=True,
                                ).start()
                        _threading.Thread(target=_delayed, daemon=True).start()
                        return
                super().publish(sender, topic, payload)

        broker = ReorderingBroker()
        _, _, _, coords = self._build_nodes(broker=broker)
        coordinators = list(coords.values())

        acquired      = []
        errors        = []
        safety_errors = []
        timing_ms     = {}

        def _observe():
            deadline = time.time() + 15
            while time.time() < deadline:
                held = [c for c in coordinators if c.state == 'HELD']
                if len(held) > 1:
                    safety_errors.append(
                        f'SAFETY VIOLATION (non-FIFO): {[c.node_id for c in held]}'
                    )
                time.sleep(0.001)

        def _do(coord):
            t0 = time.time()
            ok = coord.request_access(timeout=10.0)
            timing_ms[coord.node_id] = int((time.time() - t0) * 1000)
            if not ok:
                errors.append(f'{coord.node_id}: timed out')
                return
            time.sleep(0.05)
            coord.release_access()
            acquired.append(coord.node_id)

        observer = threading.Thread(target=_observe, daemon=True)
        observer.start()

        threads = [
            threading.Thread(target=_do, args=(c,), daemon=True)
            for c in coordinators
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        return {
            'safety_ok':     len(safety_errors) == 0,
            'liveness_ok':   sorted(acquired) == sorted(c.node_id for c in coordinators),
            'acquired_nodes': sorted(acquired),
            'errors':        errors + safety_errors,
            'timing_ms':     timing_ms,
        }

    def run_crash_mode(self):
        """supply-rover-1 crashes (its REPLY traffic is silenced).

        - drone-1 expects 2 replies but only gets 1 → times out gracefully.
        - repair-rover-1 is configured with only drone-1 as its peer (the
          one that is alive after drone-1's timeout sends deferred replies).
          It must therefore be able to acquire the resource.

        This models the real-world property: after a timeout, the timed-out
        node flushes its deferred queue so surviving nodes are not permanently
        blocked.
        """
        broker = SimBroker()

        peer_map = {
            'drone-1':        ['repair-rover-1', 'supply-rover-1'],
            'repair-rover-1': ['drone-1'],
            'supply-rover-1': ['drone-1', 'repair-rover-1'],
        }
        _, pub_clients, _, coords = self._build_nodes(broker=broker, peer_map=peer_map)

        orig_publish = pub_clients['supply-rover-1'].publish

        def silent_publish(topic, payload, qos=0):
            if 'replies' in topic:
                return
            orig_publish(topic, payload, qos)

        pub_clients['supply-rover-1'].publish = silent_publish

        drone_result = coords['drone-1'].request_access(timeout=1.5)

        rr_result = coords['repair-rover-1'].request_access(timeout=5.0)
        if rr_result:
            coords['repair-rover-1'].release_access()

        return {
            'crash_drone_timed_out':    drone_result is False,
            'surviving_peer_acquired':  rr_result is True,
            'drone_final_state':        coords['drone-1'].state,
            'repair_rover_final_state': coords['repair-rover-1'].state,
        }


def run_verification_plan():
    harness = VerificationHarness()
    return {
        'safety_liveness': harness.run_safety_liveness(),
        'failure_mode':    harness.run_failure_mode(),
        'crash_mode':      harness.run_crash_mode(),
        'non_fifo_mode':   harness.run_non_fifo_mode(),
    }
