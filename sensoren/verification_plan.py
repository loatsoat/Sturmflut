import threading
import time
from types import SimpleNamespace

from coordination import RicartAgrawalaCoordinator


class SimBroker:
    def __init__(self):
        self.clients = []

    def register(self, client):
        self.clients.append(client)

    def publish(self, sender, topic, payload):
        for client in self.clients:
            if client is sender:
                continue
            if client.matches(topic):
                client.deliver(topic, payload)


class SimMqttClient:
    def __init__(self, broker, node_id):
        self.broker = broker
        self.node_id = node_id
        self.subscriptions = []
        self.on_message = None
        self.published = []
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
    def __init__(self):
        self.broker = SimBroker()
        self.clients = []
        self.coordinators = []

    def _build_nodes(self):
        self.clients = [
            SimMqttClient(self.broker, 'drone-1'),
            SimMqttClient(self.broker, 'repair-rover-1'),
            SimMqttClient(self.broker, 'supply-rover-1'),
        ]
        self.coordinators = [
            RicartAgrawalaCoordinator('drone-1', self.clients[0], peers=['repair-rover-1', 'supply-rover-1']),
            RicartAgrawalaCoordinator('repair-rover-1', self.clients[1], peers=['drone-1', 'supply-rover-1']),
            RicartAgrawalaCoordinator('supply-rover-1', self.clients[2], peers=['drone-1', 'repair-rover-1']),
        ]
        for coordinator in self.coordinators:
            coordinator.start()

    def run_safety_liveness(self):
        self._build_nodes()
        active_holders = []
        max_concurrent = 0
        acquired = []
        timing_ms = {}

        for coordinator in self.coordinators:
            started = time.time()
            granted = coordinator.request_access(timeout=1.0)
            elapsed = int((time.time() - started) * 1000)
            timing_ms[coordinator.node_id] = elapsed
            if granted:
                active_holders.append(coordinator.node_id)
                max_concurrent = max(max_concurrent, len(active_holders))
                acquired.append(coordinator.node_id)
                time.sleep(0.05)
                coordinator.release_access()
                active_holders.remove(coordinator.node_id)

        return {
            'safety_ok': max_concurrent <= 1,
            'max_concurrent_holders': max_concurrent,
            'acquired_nodes': acquired,
            'liveness_ok': sorted(acquired) == ['drone-1', 'repair-rover-1', 'supply-rover-1'],
            'timing_ms': timing_ms,
        }

    def run_failure_mode(self):
        self._build_nodes()

        class LossyBroker(SimBroker):
            def __init__(self, original, drop_topic):
                super().__init__()
                self.original = original
                self.drop_topic = drop_topic
                self.dropped = 0

            def publish(self, sender, topic, payload):
                if topic == self.drop_topic:
                    self.dropped += 1
                    return
                return super().publish(sender, topic, payload)

        # Rebuild with a lossy broker for a single request.
        broker = LossyBroker(self.broker, 'vehicles/coordination/replies/charging_station')
        clients = [
            SimMqttClient(broker, 'drone-1'),
            SimMqttClient(broker, 'repair-rover-1'),
            SimMqttClient(broker, 'supply-rover-1'),
        ]
        coordinators = [
            RicartAgrawalaCoordinator('drone-1', clients[0], peers=['repair-rover-1', 'supply-rover-1']),
            RicartAgrawalaCoordinator('repair-rover-1', clients[1], peers=['drone-1', 'supply-rover-1']),
            RicartAgrawalaCoordinator('supply-rover-1', clients[2], peers=['drone-1', 'repair-rover-1']),
        ]
        for coordinator in coordinators:
            coordinator.start()

        result = coordinators[0].request_access(timeout=1.0)
        return {
            'failure_ok': result is False,
            'dropped_messages': broker.dropped,
            'final_state': coordinators[0].state,
        }


def run_verification_plan():
    harness = VerificationHarness()
    safety_liveness = harness.run_safety_liveness()
    failure_mode = harness.run_failure_mode()
    return {
        'safety_liveness': safety_liveness,
        'failure_mode': failure_mode,
    }
