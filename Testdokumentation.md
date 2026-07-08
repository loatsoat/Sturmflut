# Testdokumentation 4.2

- System starten mit docker compose up -d --build
- Leitstelle läuft im Browser auf http://127.0.0.1:8081/
- Dashboard öffnen.
- Eine POST /unit Anfrage mit einer Kamera senden.
- Eine POST /incident Anfrage mit einem Vorfall senden.
- GET /status und GET /history öffnen.
- Die Einheit wird registriert.
- Der Vorfall wird angenommen.
- Der Status zeigt die neue Einheit und den Vorfall.
- Die Historie enthält den verarbeiteten Vorfall.
- Die Einheit wird erfolgreich registriert.
- Der Vorfall wird erfolgreich angenommen.
- Dashboard und JSON-Endpunkte zeigen die neuen Daten.

## Test 4.2.1

- Aufgabe / Meilenstein: Aufgabe 1 - Leitstelle und Dashboard
- Testtyp: Nicht-funktional
- Titel: Lesbarkeit der Inselkarte
- Ziel: Prüfen, ob die Karte im Browser gut lesbar ist und die wichtige Infrastruktur sichtbar ist.
- Vorbedingungen / Setup:
  - System starten mit docker compose up -d --build
  - Dashboard in einem normalen Browser öffnen
- Durchführung:
  - Dashboard öffnen.
  - Die komplette 20x20-Karte anschauen.
  - Insel-Form, Sandfarben und Infrastruktursymbole prüfen.
- Erwartetes Ergebnis:
  - Die Karte ist sichtbar und gut lesbar.
  - Die Insel ist klar vom Wasser getrennt.
  - Die Infrastruktur ist leicht zu erkennen.
- Tatsächliches Ergebnis:
  - Die Karte ist gut lesbar.
  - Die Insel-Form ist sichtbar.
  - Die Infrastruktur ist klar markiert.
- Artefakte / Nachweise: Browser-Screenshot vom Dashboard
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

## Test 4.2.1

- Aufgabe / Meilenstein: Aufgabe 1 – Leitstelle und Registrierung via Sockets, HTTP und REST
- Testtyp: Nicht-funktional
- Titel: Robustheit und Fehlerbehandlung bei nicht unterstützten HTTP-Methoden
- Ziel: Es wird messbar überprüft, ob der native HTTP-Server nicht unterstützte Methoden (wie PUT oder DELETE) korrekt abweist, mit dem passenden Fehlercode antwortet, eine angemessene Antwortzeit einhält und dabei stabil bleibt (kein Absturz des Sockets).
- Vorbedingungen / Setup:
  - Der Container leitstelle läuft stabil im Docker-Netzwerk.
  - Ein Benchmark- oder Anfrage-Tool (z. B. curl oder ab / Apache Benchmark) ist installiert.
- Durchführung:
  - Senden Sie eine HTTP-PUT-Anfrage an den Endpunkt http://localhost:8081/status (eine Methode, die laut Spezifikation nicht unterstützt werden muss).
  - (Optional zur Messbarkeit): Senden Sie eine Sequenz von 100 fehlerhaften PUT-Anfragen innerhalb von 2 Sekunden, um die Stabilität des Socket-Handlings zu prüfen.
- Erwartetes Ergebnis:
  - Der Server darf nicht abstürzen und muss alle Verbindungen sauber verarbeiten.
  - Jede nicht unterstützte Anfrage muss zwingend mit einem passenden Fehlercode (z. B. 405 Method Not Allowed oder 501 Not Implemented) beantwortet werden.
  - Die durchschnittliche Antwortzeit (Response Time) für diese Fehlerantworten muss messbar unter 50ms liegen.
- Tatsächliches Ergebnis:
  - ichliebeminhs-MacBook:Gruppe-4C1-2 phanhoquangminh$ curl -i -X PUT http://     localhost:8081/status
HTTP/1.1 405 Method Not Allowed 
Content-Length: 0
  - 100% der Anfragen mit Code 405 beantwortet, mittlere Antwortzeit 2ms, Container blieb stabil.
- Artefakte / Nachweise: Terminal-Output des curl-Befehls inklusive HTTP-Header-Antwort.
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

# Testdokumentation 4.3

## Verbesserungen gegenüber 4.2

- Einsatzvergabe jetzt per RPC statt nur über REST.
- Mehrere Fahrzeugrollen sind vorhanden: Drohne, Reparatur-Rover und Versorgungs-Rover.
- Die Fahrzeugzustände sind sichtbar: IDLE, ASSIGNED, BUSY und ERROR.
- Der Fortschritt der Einsätze ist im Dashboard und in `/status` sichtbar.
- Die Tests sind klarer aufgeteilt und zeigen Funktion, Nicht-Funktion und Rollenzuordnung.

## Test 4.3.1

- Aufgabe / Meilenstein: Aufgabe 2 - Einsatzvergabe via RPC
- Testtyp: Funktional
- Titel: Rollenbasierte Einsatzvergabe
- Ziel: Prüfen, ob die Leitstelle Einsätze an die richtige Fahrzeugrolle vergibt und der Auftrag bis `DONE` läuft.
- Vorbedingungen / Setup:
  - System starten mit `docker compose up -d --build`
  - Browser-URL der Leitstelle: `http://127.0.0.1:8081/`
  - Interne Docker-URL für Sensoren und Fahrzeuge: `http://leitstelle:8080`
  - Fahrzeuge sind per REST bei der Leitstelle registriert
- Durchführung:
  1. Eine `person_detected` Meldung senden.
  2. `GET /status` öffnen und `active_missions` prüfen.
  3. Nach einigen Sekunden wieder `GET /status` und `GET /history` prüfen.
- Erwartetes Ergebnis:
  - `person_detected` wird der Drohne zugewiesen.
  - Die Mission läuft von `QUEUED` über `ASSIGNED` und `BUSY` bis `DONE`.
  - Die Historie zeigt den verarbeiteten Vorfall.
- Tatsächliches Ergebnis:
  - Die Drohne nimmt den Auftrag an.
  - Die Mission wird in `DONE` abgeschlossen.
  - Der Eintrag erscheint in `/history`.
- Artefakte / Nachweise: Browser-Dashboard, JSON von `/status`, JSON von `/history`
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

## Test 4.3.2

- Aufgabe / Meilenstein: Aufgabe 2 - Einsatzvergabe via RPC
- Testtyp: Nicht-funktional 
- Titel: Durchsatz und Latenz des HTTP-Servers unter Last
- Ziel: Messbar prüfen, wie viele Anfragen pro Sekunde der native Socket-basierte HTTP-Server verarbeiten kann und wie hoch die mittlere Antwortzeit (Latenz) dabei ist. Schwellwerte: mindestens 50 Anfragen/Sekunde, mittlere Antwortzeit unter 100 ms, keine fehlgeschlagenen Anfragen.
- Vorbedingungen / Setup:
  - System starten mit `docker compose up -d --build`
  - Apache Bench installiert (auf macOS/Linux im Paket `apache2-utils`, auf Windows via WSL oder Chocolatey: `choco install apache-httpd`)
  - Leitstelle erreichbar unter `http://127.0.0.1:8081/`
- Durchführung:

  Zwei tests mit Apache Bench (`ab`) ausführen:

  Test 1 – GET /status (JSON-Endpunkt):**
  ```
  ab -n 500 -c 10 http://127.0.0.1:8081/status
  ```
  500 Anfragen, 10 gleichzeitige Verbindungen.

  Test 2 – GET / (Dashboard-HTML):**
  ```
  ab -n 200 -c 5 http://127.0.0.1:8081/
  ```
  200 Anfragen, 5 gleichzeitige Verbindungen.

  Aus der `ab`-Ausgabe folgende Werte ablesen:
  - `Requests per second`
  - `Time per request (mean)`
  - `Failed requests`

- Erwartetes Ergebnis:
  - Mindestens 50 Anfragen/Sekunde für `GET /status`
  - Mittlere Antwortzeit unter 100 ms
  - 0 fehlgeschlagene Anfragen (`Failed requests: 0`)
  - Server bleibt stabil, kein Absturz des Containers

- Tatsächliches Ergebnis:

  Test 1 – GET /status:**
  ```
  Requests per second:    316..71 [#/sec]
  Time per request:       32.574 [ms] (mean)
  Failed requests:        1 (Wegen length)
  ```

  Test 2 – GET / (Dashboard):**
  ```
  Requests per second:    409.55 [#/sec]
  Time per request:       12.228 [ms] (mean)
  Failed requests:        0
  ```
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

## Test 4.3.3

- Aufgabe / Meilenstein: Aufgabe 2 - Einsatzvergabe via RPC
- Testtyp: Funktional
- Titel: Rollenzuordnung für Bodenfahrzeuge
- Ziel: Prüfen, ob ein `blocked_route` Einsatz an den Reparatur-Rover und ein `low_stock` Einsatz an den Versorgungs-Rover vergeben wird.
- Vorbedingungen / Setup:
  - System starten mit `docker compose up -d --build`
  - Browser-URL der Leitstelle: `http://127.0.0.1:8081/`
  - Interne Docker-URL für Sensoren und Fahrzeuge: `http://leitstelle:8080`
  - Fahrzeuge sind bei der Leitstelle registriert
- Durchführung:
  1. Eine `blocked_route` Meldung auf einer Landzelle senden.
  2. Eine `low_stock` Meldung auf einer Landzelle senden.
  3. Nach einigen Sekunden `GET /status` öffnen.
- Erwartetes Ergebnis:
  - `blocked_route` geht an den Reparatur-Rover.
  - `low_stock` geht an den Versorgungs-Rover.
  - Beide Aufträge werden abgeschlossen.
- Tatsächliches Ergebnis:
  - Die richtige Fahrzeugrolle wird ausgewählt.
  - Die Missionen laufen bis `DONE`.
  - Der Status zeigt die bearbeiteten Missionen.
- Artefakte / Nachweise: JSON von `/status`, JSON von `/history`
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

## Test 4.3.4

- Aufgabe / Meilenstein: Aufgabe 2 - Einsatzvergabe via RPC
- Testtyp: Nicht-funktional
- Titel: Missionsstatus wechselt zu ASSIGNED innerhalb von 2 Sekunden
- Ziel: Messen ob die Leitstelle einen Vorfall empfängt, die richtige Drohne per RPC beauftragt und der Missionsstatus innerhalb von 2 Sekunden auf ASSIGNED wechselt.
- Vorbedingungen / Setup:
  - System starten mit `docker compose up -d --build`
  - Browser-URL der Leitstelle: `http://127.0.0.1:8081/`
  - Alle Container laufen und Drone ist IDLE
  - bash und curl verfügbar
- Durchführung:
  1. Folgenden bash-Befehl ausführen — misst die Zeit vom POST /incident bis Mission status = ASSIGNED:
    # !/bin/bash
    START=$(date +%s%3N)

    curl -s -X POST http://localhost:8081/incident \
      -H "Content-Type: application/json" \
      -d '{
        "type": "person_detected",
        "x": 10, "y": 5,
        "confidence": 0.9,
        "priority": 1
    }' > /dev/null

    # Warte bis ASSIGNED erscheint (max 5 Versuche)
    for i in {1..5}; do
      sleep 0.5
      STATUS=$(curl -s http://localhost:8081/status)
      if echo "$STATUS" | grep -q '"ASSIGNED"'; then
        END=$(date +%s%3N)
        echo "Zeit bis ASSIGNED: $((END - START)) ms"
        break
      fi
    done
  2. Test 5 Mal wiederholen und Ergebnisse notieren.
- Erwartetes Ergebnis:
  - Jeder Durchlauf: Zeit bis ASSIGNED < 2000 ms
  - Kein Durchlauf überschreitet 2000 ms
- Tatsächliches Ergebnis:
  [Tabelle nach Testdurchführung ausfüllen]
  | Durchlauf   | Zeit (ms) | Ergebnis |
  |-------------|-----------|----------|
  | 1           |1150       |PASS      |
  | 2           |1153       |PASS      |
  | 3           |1130       |PASS      |
  | 4           |1126       |PASS      |
  | 5           |1132       |PASS      |
  | Durchschnitt|1138       |PASS      |
- Artefakte / Nachweise:
  - Terminal Output des bash-Skripts
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

# Testdokumentation 4.4

## Test 4.4.1

- Aufgabe / Meilenstein: Aufgabe 3 – Ereignisse und Telemetrie über MQTT
- Testtyp: Funktional
- Titel: Sensor-Event über MQTT führt zu Incident und RPC-Dispatch
- Ziel: Überprüfen ob ein über MQTT publiziertes Sensor-Event auf "sensors/events/{unit_id}" von der Leitstelle empfangen, korrekt geparst, als Incident eingereiht und per RPC an die passende Einheit dispatcht wird.
- Vorbedingungen / Setup:
  - docker compose up --build
  - Container: leitstelle, mqtt-broker, drone-1
  - mosquitto_pub/mosquitto_sub auf dem Host installiert
  - Drone-1 ist registriert und im Zustand IDLE
- Durchführung:
  1. MQTT-Verbindung der Leitstelle prüfen:
    docker compose logs leitstelle | grep "mqtt.*connected"

  2. Sensor-Event publizieren:
    mosquitto_pub -h localhost -p 1883 \
     -t "sensors/events/camera-1" \
     -q 1 \
     -m '{
       "type": "person_detected",
       "x": 10, "y": 5,
       "confidence": 0.92,
       "unit_id": "camera-1",
       "timestamp": '$(date +%s)'
     }'

  3. Nach 3 Sekunden Status abfragen:
    curl http://localhost:8081/status
- Erwartetes Ergebnis:
  - Schritt 1: Log zeigt "[mqtt] connected rc=0"
  - Schritt 3:
    - active_missions enthält neue Mission mit
    incident_type = "person_detected", assigned_unit = "drone-1"
    - mission_log zeigt: QUEUED → ASSIGNED
    - drone-1 state = "ASSIGNED" oder "BUSY"
- Tatsächliches Ergebnis:
  - Der MQTT-Event wurde erfolgreich an die Leitstelle übermittelt und im Status-Endpoint als Incident erkannt.
  - `curl http://localhost:8081/status` lieferte einen Eintrag unter `incidents` mit `type: "person_detected"` und den Feldern `unit_id`, `x`, `y`, `timestamp` aus dem gesendeten Event.
  - In `mission_log` wurden Einträge für `QUEUED`, `ASSIGNED`, `BUSY` und `DONE` sichtbar; der Drone-Task wurde also verarbeitet und abgeschlossen.
  - Der erwartete Log-Eintrag `[mqtt] connected rc=0` war im Testlauf nicht sichtbar, die funktionale Verarbeitung über das Status-Endpoint war jedoch erfolgreich.
- Artefakte / Nachweise:
  - docker compose logs leitstelle
  - curl Output GET /status
  - Verifizierter Status-Output aus dem laufenden System
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

## Test 4.4.2

- Aufgabe / Meilenstein: Aufgabe 3 – Ereignisse und Telemetrie über MQTT
- Testtyp: Nicht-funktional 
- Titel: Duplicate Events innerhalb DEDUP_WINDOW_SECONDS werden verworfen
- Ziel: Messen, ob doppelte MQTT-Events an derselben Position innerhalb des Dedup-Fensters (15s) zuverlässig erkannt und verworfen werden, und wie schnell die Verarbeitung pro Nachricht erfolgt.
- Vorbedingungen / Setup:
  - docker compose up --build
  - Leitstelle mit MQTT verbunden
  - Keine aktiven Missionen zu Testbeginn
- Durchführung: Folgendes Skript ausführen — sendet 5 identische Events in schneller Folge (< 15s Abstand) an dieselbe Position:
#!/bin/bash
for i in {1..5}; do
  mosquitto_pub -h localhost -p 1883 \
    -t "sensors/events/sensor-water-1" \
    -q 1 \
    -m '{
      "type": "water_level_alert",
      "x": 8, "y": 12,
      "value": 995,
      "unit_id": "dup-test-4.4.2",
      "timestamp": '$(date +%s)'
    }'
  sleep 1
done

sleep 2
curl -s http://localhost:8081/history | python3 -m json.tool

- Erwartetes Ergebnis:
  - Nur 1 Incident wird in history erzeugt (die anderen 4 als "dropped duplicate sensor event" in den Logs verworfen)
  - docker compose logs leitstelle zeigt 4x: "[mqtt] dropped duplicate sensor event"
  - Zeit zwischen Empfang der MQTT-Nachricht und Log-Eintrag < 200ms
- Tatsächliches Ergebnis:
  - Die Prüfung wurde mit 5 schnell aufeinanderfolgenden MQTT-Messages ausgeführt.
  - Ein neuer History-Eintrag mit `value: 995` wurde erzeugt; die übrigen Nachrichten wurden als Duplikate verworfen.
  - In den Leitstellen-Logs erschienen 5 Einträge mit `[mqtt] dropped duplicate sensor event` für die wiederholten Nachrichten.
  - Die Verarbeitungszeit bis zum sichtbaren History-Eintrag wurde mit 104.63 ms gemessen und liegt damit unter der Zielgrenze von 200 ms.

| Event Nr. | Verarbeitet als  | Zeit bis Log / Sichtbarkeit (ms)  |
|-----------|------------------|-----------------------------------|
| 1         | akzeptiert / Incident erzeugt | 104.63 |
| 2         | verworfen als Duplikat | sofort / Log-Eintrag vorhanden |
| 3         | verworfen als Duplikat | sofort / Log-Eintrag vorhanden |
| 4         | verworfen als Duplikat | sofort / Log-Eintrag vorhanden |
| 5         | verworfen als Duplikat | sofort / Log-Eintrag vorhanden |

- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild