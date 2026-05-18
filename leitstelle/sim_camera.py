import os
import time
import random
import requests

HOST = os.environ.get('LEITSTELLE','http://127.0.0.1:8080')

def register():
    payload = {'id':'camera-1','role':'camera','x':12,'y':8}
    try:
        requests.post(HOST + '/unit', json=payload, timeout=2)
    except Exception:
        pass

def run():
    register()
    while True:
        # simulate person confidence
        confidence = random.random()
        print('person confidence:', confidence)
        if confidence > 0.95:
            incident = {'type':'person_detected','confidence': confidence, 'x':12, 'y':8, 'priority':1}
            try:
                requests.post(HOST + '/incident', json=incident, timeout=2)
                print('sent incident', incident)
            except Exception as e:
                print('send failed', e)
        # simulate blocked route detection
        if random.random() < 0.05:
            incident = {'type':'blocked_route','description':'debris','x':10,'y':9,'priority':2}
            try:
                requests.post(HOST + '/incident', json=incident, timeout=2)
                print('sent incident', incident)
            except Exception as e:
                print('send failed', e)
        time.sleep(2)

if __name__ == '__main__':
    run()
