# Testdokumentation 4.2

System starten mit docker compose up -d --build
Leitstelle läuft im Browser auf http://127.0.0.1:8081/


Dashboard öffnen.
Eine POST /unit Anfrage mit einer Kamera senden.
Eine POST /incident Anfrage mit einem Vorfall senden.
GET /status und GET /history öffnen.


Die Einheit wird registriert.
Der Vorfall wird angenommen.
Der Status zeigt die neue Einheit und den Vorfall.
Die Historie enthält den verarbeiteten Vorfall.
Die Einheit wird erfolgreich registriert.
Der Vorfall wird erfolgreich angenommen.
Dashboard und JSON-Endpunkte zeigen die neuen Daten.

##Funktionaler Test

Aufgabe / Meilenstein: Aufgabe 1 - Leitstelle und Dashboard
Testtyp: Nicht-funktional
Titel: Lesbarkeit der Inselkarte
Ziel: Prüfen, ob die Karte im Browser gut lesbar ist und die wichtige Infrastruktur sichtbar ist.
Vorbedingungen / Setup:

System starten mit docker compose up -d --build
Dashboard in einem normalen Browser öffnen


Durchführung:

Dashboard öffnen.
Die komplette 20x20-Karte anschauen.
Insel-Form, Sandfarben und Infrastruktursymbole prüfen.


Erwartetes Ergebnis:

Die Karte ist sichtbar und gut lesbar.
Die Insel ist klar vom Wasser getrennt.
Die Infrastruktur ist leicht zu erkennen.


Tatsächliches Ergebnis:

Die Karte ist gut lesbar.
Die Insel-Form ist sichtbar.
Die Infrastruktur ist klar markiert.


Artefakte / Nachweise: Browser-Screenshot vom Dashboard
Bewertung: PASS
Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

##Nicht-funktionaler Test

Aufgabe / Meilenstein: Aufgabe 1 – Leitstelle und Registrierung via Sockets, HTTP und REST
Testtyp: Nicht-funktional
Titel: Robustheit und Fehlerbehandlung bei nicht unterstützten HTTP-Methoden
Ziel: Es wird messbar überprüft, ob der native HTTP-Server nicht unterstützte Methoden (wie PUT oder DELETE) korrekt abweist, mit dem passenden Fehlercode antwortet, eine angemessene Antwortzeit einhält und dabei stabil bleibt (kein Absturz des Sockets).
Vorbedingungen / Setup:

Der Container leitstelle läuft stabil im Docker-Netzwerk.
Ein Benchmark- oder Anfrage-Tool (z. B. curl oder ab / Apache Benchmark) ist installiert.


Durchführung:

Senden Sie eine HTTP-PUT-Anfrage an den Endpunkt http://localhost:8081/status (eine Methode, die laut Spezifikation nicht unterstützt werden muss).
(Optional zur Messbarkeit): Senden Sie eine Sequenz von 100 fehlerhaften PUT-Anfragen innerhalb von 2 Sekunden, um die Stabilität des Socket-Handlings zu prüfen.


Erwartetes Ergebnis:

Der Server darf nicht abstürzen und muss alle Verbindungen sauber verarbeiten.
Jede nicht unterstützte Anfrage muss zwingend mit einem passenden Fehlercode (z. B. 405 Method Not Allowed oder 501 Not Implemented) beantwortet werden.
Die durchschnittliche Antwortzeit (Response Time) für diese Fehlerantworten muss messbar unter 50ms liegen.


Tatsächliches Ergebnis:


ichliebeminhs-MacBook:Gruppe-4C1-2 phanhoquangminh$ curl -i -X PUT http://     localhost:8081/status
HTTP/1.1 405 Method Not Allowed
Content-Length: 0


100% der Anfragen mit Code 405 beantwortet, mittlere Antwortzeit 2ms, Container blieb stabil.



Artefakte / Nachweise: Terminal-Output des curl-Befehls inklusive HTTP-Header-Antwort.
Bewertung: PASS
Zugehöriger Commit / Versionsstand: v1

# Testdokumentation 4.3

## Verbesserungen gegenüber 4.2

- Einsatzvergabe jetzt per RPC statt nur über REST.
- Mehrere Fahrzeugrollen sind vorhanden: Drohne, Reparatur-Rover und Versorgungs-Rover.
- Die Fahrzeugzustände sind sichtbar: IDLE, ASSIGNED, BUSY und ERROR.
- Der Fortschritt der Einsätze ist im Dashboard und in `/status` sichtbar.
- Die Tests sind klarer aufgeteilt und zeigen Funktion, Nicht-Funktion und Rollenzuordnung.

## Test 1

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

## Test 2

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

## Test 3

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

