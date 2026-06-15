#!/usr/bin/env python3
"""Trigger an incident at the Leitstelle for testing assignment.

Usage: python tools/trigger_incident.py [type] [x] [y] [priority]
Example: python tools/trigger_incident.py blocked_route 12 8 1
"""
import os
import sys
import json
from urllib import request

HOST = os.environ.get('LEITSTELLE', 'http://127.0.0.1:8081')


def post_json(url, payload, timeout=3):
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()


def main():
    if len(sys.argv) < 4:
        print('Usage: trigger_incident.py type x y [priority]')
        return
    itype = sys.argv[1]
    x = int(sys.argv[2])
    y = int(sys.argv[3])
    prio = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    payload = {'type': itype, 'x': x, 'y': y, 'priority': prio}
    url = HOST.rstrip('/') + '/incident'
    try:
        out = post_json(url, payload)
        print('Posted:', out)
    except Exception as exc:
        print('Failed to post incident:', exc)


if __name__ == '__main__':
    main()
