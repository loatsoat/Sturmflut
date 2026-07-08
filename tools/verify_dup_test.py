import json
import subprocess
import time
import urllib.request

base_url = 'http://localhost:8081/history'
with urllib.request.urlopen(base_url, timeout=5) as r:
    before = json.load(r)

for _ in range(5):
    payload = {
        'type': 'water_level_alert',
        'x': 8,
        'y': 12,
        'value': 995,
        'unit_id': 'dup-test-4.4.2',
        'timestamp': int(time.time()),
    }
    msg = json.dumps(payload)
    cmd = [
        'docker', 'run', '--rm', '--network', 'gruppe-4c1-2_default',
        'eclipse-mosquitto:2.0', 'mosquitto_pub', '-h', 'mqtt-broker', '-p', '1883',
        '-t', 'sensors/events/sensor-water-1', '-q', '1', '-m', msg
    ]
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)

start = time.time()
for _ in range(20):
    time.sleep(0.1)
    with urllib.request.urlopen(base_url, timeout=5) as r:
        data = json.load(r)
    if any(item.get('value') == 995 for item in data.get('history', [])):
        break
else:
    data = {'history': []}

latency_ms = (time.time() - start) * 1000
new_entries = [item for item in data.get('history', []) if item.get('value') == 995]
print('latency_ms=', round(latency_ms, 2))
print('new_entries_count=', len(new_entries))
print('matching_history_entries=')
for item in new_entries:
    print(item)
print('recent_duplicate_logs=')
logs = subprocess.check_output(['docker', 'compose', 'logs', 'leitstelle'], text=True, stderr=subprocess.STDOUT)
for line in logs.splitlines()[-20:]:
    if 'dropped duplicate sensor event' in line:
        print(line)
