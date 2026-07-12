import json
import os
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sensoren'))

from coordination import RicartAgrawalaCoordinator


class DummyClient:
    def __init__(self):
        self.messages = []
        self.subscriptions = []
        self.on_message = None

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))

    def publish(self, topic, payload, qos=0):
        self.messages.append((topic, payload, qos))


def run_demo():
    a = DummyClient()
    b = DummyClient()
    c = DummyClient()
    ca = RicartAgrawalaCoordinator('drone-1', a, peers=['repair-rover-1', 'supply-rover-1'])
    cb = RicartAgrawalaCoordinator('repair-rover-1', b, peers=['drone-1', 'supply-rover-1'])
    cc = RicartAgrawalaCoordinator('supply-rover-1', c, peers=['drone-1', 'repair-rover-1'])
    ca.start(); cb.start(); cc.start()

    def request_access(coordinator):
        ok = coordinator.request_access(timeout=1.5)
        if ok:
            time.sleep(0.2)
            coordinator.release_access()

    t1 = threading.Thread(target=request_access, args=(ca,), daemon=True)
    t2 = threading.Thread(target=request_access, args=(cb,), daemon=True)
    t3 = threading.Thread(target=request_access, args=(cc,), daemon=True)
    t1.start(); t2.start(); t3.start()
    t1.join(); t2.join(); t3.join()

    print('demo complete')
    print('states:', ca.state, cb.state, cc.state)
    print('messages:', len(a.messages) + len(b.messages) + len(c.messages))


if __name__ == '__main__':
    run_demo()
