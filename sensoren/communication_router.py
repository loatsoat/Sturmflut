import json
import os
from urllib import error, request

from http_utils import post_json


class CommunicationRouter:
    """Choose between MQTT and HTTP for vehicle message delivery."""

    def __init__(self, mqtt_client=None, http_url=None, max_mqtt_payload_bytes=12000):
        self.mqtt_client = mqtt_client
        self.http_url = http_url or os.environ.get('LEITSTELLE', 'http://127.0.0.1:8080')
        self.max_mqtt_payload_bytes = max_mqtt_payload_bytes
        self.last_error = None

    def send(self, message_type, payload, prefer='auto'):
        self.last_error = None
        if prefer == 'http':
            return self._send_http(message_type, payload)
        if prefer == 'mqtt':
            return self._send_mqtt(message_type, payload)

        if self._should_use_http(payload):
            return self._send_http(message_type, payload)
        return self._send_mqtt(message_type, payload)

    def _send_mqtt(self, message_type, payload):
        if self.mqtt_client is None:
            self.last_error = 'mqtt unavailable'
            return self._send_http(message_type, payload)
        try:
            topic = self._topic_for(message_type)
            self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
            return {'ok': True, 'channel': 'mqtt', 'topic': topic}
        except Exception as exc:
            self.last_error = str(exc)
            return self._send_http(message_type, payload)

    def _send_http(self, message_type, payload):
        try:
            url = self._url_for(message_type)
            post_json(url, payload)
            return {'ok': True, 'channel': 'http', 'url': url}
        except (error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as exc:
            self.last_error = str(exc)
            return {'ok': False, 'channel': 'http', 'error': str(exc)}

    def _should_use_http(self, payload):
        if self.mqtt_client is None:
            return True
        try:
            size = len(json.dumps(payload).encode('utf-8'))
        except Exception:
            return True
        return size > self.max_mqtt_payload_bytes

    def _topic_for(self, message_type):
        mapping = {
            'telemetry': 'vehicles/telemetry/router',
            'mission': 'vehicles/missions/router',
            'coordination': 'vehicles/coordination/router',
        }
        return mapping.get(message_type, 'vehicles/messages/router')

    def _url_for(self, message_type):
        if message_type == 'mission':
            return f"{self.http_url}/mission_update"
        return f"{self.http_url}/unit"
