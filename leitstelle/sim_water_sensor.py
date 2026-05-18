import os
import time
import random
import requests

HOST = os.environ.get('LEITSTELLE','http://127.0.0.1:8080')

def register():
    payload = {'id':'water-sensor-1','role':'water_sensor','x':6,'y':6}
    try:
        requests.post(HOST + '/unit', json=payload, timeout=2)
    except Exception:
        pass

def run():
    register()
    while True:
        # simulate water level in cm
        level = random.gauss(50, 20)
        print('water level:', level)
        if level > 90:
            incident = {'type':'water_level_alert','value': level, 'x':6, 'y':6, 'priority':2}
            try:
                requests.post(HOST + '/incident', json=incident, timeout=2)
                print('sent incident', incident)
            except Exception as e:
                print('send failed', e)
        time.sleep(3)

if __name__ == '__main__':
    run()
