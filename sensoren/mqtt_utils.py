import json
import os
import time

import paho.mqtt.client as mqtt

MQTT_BROKER = os.environ.get('MQTT_BROKER', '127.0.0.1')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
_CONNECT_RETRIES = 10
_RETRY_DELAY = 2


def build_client(client_id: str) -> mqtt.Client:
    """Create and connect a paho MQTT client with auto-reconnect."""
    client = mqtt.Client(client_id=client_id, clean_session=True)
    client.reconnect_delay_set(min_delay=1, max_delay=16)

    for attempt in range(_CONNECT_RETRIES):
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
            client.loop_start()
            print(f'[mqtt_utils] connected to {MQTT_BROKER}:{MQTT_PORT} as {client_id}')
            return client
        except Exception as exc:
            print(f'[mqtt_utils] connect attempt {attempt + 1} failed: {exc}')
            time.sleep(_RETRY_DELAY)

    print('[mqtt_utils] WARNING: could not connect to MQTT broker – running without MQTT')
    return client


def publish_event(client: mqtt.Client, unit_id: str, payload: dict) -> None:
    topic = f'sensors/events/{unit_id}'
    _publish(client, topic, payload, qos=1)


def publish_telemetry(client: mqtt.Client, unit_id: str, payload: dict) -> None:
    topic = f'vehicles/telemetry/{unit_id}'
    _publish(client, topic, payload, qos=0)


def publish_mission(client: mqtt.Client, unit_id: str, payload: dict) -> None:
    topic = f'vehicles/missions/{unit_id}'
    _publish(client, topic, payload, qos=1)


def publish_coordination(client: mqtt.Client, resource_id: str, phase: str, payload: dict) -> None:
    topic = f'vehicles/coordination/{phase}/{resource_id}'
    _publish(client, topic, payload, qos=1)


def _publish(client: mqtt.Client, topic: str, payload: dict, qos: int) -> None:
    try:
        msg = json.dumps(payload)
        client.publish(topic, msg, qos=qos)
    except Exception as exc:
        print(f'[mqtt_utils] publish failed on {topic}: {exc}')
