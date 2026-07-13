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
        broker = SimBroker()
        _, _, _, coords = self._build_nodes(broker=broker)
        coordinators = list(coords.values())

        max_concurrent = [0]
        concurrent_lock = threading.Lock()
        safety_errors   = []

        def _observe():
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


    def run_latency_smoke(self):
        RUNS = 10

        latencies = []
        timeouts  = 0

        for _ in range(RUNS):
            broker = SimBroker()
            _, _, _, coords = self._build_nodes(broker=broker)
            coord = coords['drone-1']

            t0 = time.perf_counter()
            ok = coord.request_access(timeout=5.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if ok:
                coord.release_access()
                latencies.append(elapsed_ms)
            else:
                timeouts += 1

        latencies.sort()
        n = len(latencies)
        p50 = latencies[int(n * 0.50)] if n else float('inf')
        p95 = latencies[int(n * 0.95)] if n else float('inf')

        return {
            'runs':         RUNS,
            'timeouts':     timeouts,
            'p50_ms':       round(p50, 2),
            'p95_ms':       round(p95, 2),
            'all_ms':       [round(x, 2) for x in latencies],
            'latency_ok':   timeouts == 0 and p50 < 50 and p95 < 100,
        }


def run_verification_plan():
    harness = VerificationHarness()
    return {
        'safety_liveness': harness.run_safety_liveness(),
        'failure_mode':    harness.run_failure_mode(),
        'crash_mode':      harness.run_crash_mode(),
        'non_fifo_mode':   harness.run_non_fifo_mode(),
        'latency_smoke':   harness.run_latency_smoke(),
    }
