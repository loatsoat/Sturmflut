import json
from urllib import request


def post_json(url, payload, timeout=2):
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with request.urlopen(req, timeout=timeout):
        return True
