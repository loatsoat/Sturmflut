# Testdokumentation 4.2

## Test 1

  - System starten mit `docker compose up -d --build`
  - Browser-URL der Leitstelle: `http://127.0.0.1:8081/`
  - Interne Docker-URL für Sensoren und Fahrzeuge: `http://leitstelle:8080`
  1. Dashboard öffnen.
  2. Eine `POST /unit` Anfrage mit einer Kamera senden.
  3. Eine `POST /incident` Anfrage mit einem Vorfall senden.
  4. `GET /status` und `GET /history` öffnen.
  - Die Einheit wird registriert.
  - Der Vorfall wird angenommen.
  - Der Status zeigt die neue Einheit und den Vorfall.
  - Die Historie enthält den verarbeiteten Vorfall.
  - Die Einheit wird erfolgreich registriert.
  - Der Vorfall wird erfolgreich angenommen.
  - Dashboard und JSON-Endpunkte zeigen die neuen Daten.

## Funktionaler Test

- Aufgabe / Meilenstein: Aufgabe 1 - Leitstelle und Dashboard
- Testtyp: Nicht-funktional
- Titel: Lesbarkeit der Inselkarte
- Ziel: Prüfen, ob die Karte im Browser gut lesbar ist und die wichtige Infrastruktur sichtbar ist.
- Vorbedingungen / Setup:
  - System starten mit `docker compose up -d --build`
  - Dashboard in einem normalen Browser öffnen
- Durchführung:
  1. Dashboard öffnen.
  2. Die komplette 20x20-Karte anschauen.
  3. Insel-Form, Sandfarben und Infrastruktursymbole prüfen.
- Ergebnis:
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

## Test 3

- Aufgabe / Meilenstein: Aufgabe 1 - Leitstelle und Sensoren
- Testtyp: Funktional
- Titel: Anzeige von Personenerkennung im Protokoll
- Ziel: Prüfen, ob eine Personenerkennung im Verlauf und in der Historie sichtbar ist.
- Vorbedingungen / Setup:
  - System starten mit `docker compose up -d --build`
  - Eine Kameraeinheit ist verbunden
- Durchführung:
  1. Dashboard öffnen.
  2. Eine Personenerkennung über die Kamera auslösen.
  3. Die Incident-Historie im Dashboard ansehen.
- Erwartetes Ergebnis:
  - Der Vorfall wird gespeichert.
  - Der Wert für die Erkennung ist sichtbar.
  - Die Historie zeigt einen verständlichen Eintrag.
- Tatsächliches Ergebnis:
  - Der Vorfall wird gespeichert.
  - Der Confidence-Wert ist sichtbar.
  - Die Historie zeigt einen klaren Eintrag.
- Artefakte / Nachweise: Browser-Dashboard, Eintrag in `/history`
- Bewertung: PASS
- Zugehöriger Commit / Versionsstand: Lokaler Workspace nach dem letzten Rebuild

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
- Titel: Lesbarkeit vom Mission-Dashboard
- Ziel: Prüfen, ob die Einheiten, Missionen und der Fortschritt im Dashboard gut lesbar sind.
- Vorbedingungen / Setup:
  - System starten mit `docker compose up -d --build`
  - Browser-URL der Leitstelle: `http://127.0.0.1:8081/`
  - Interne Docker-URL für Sensoren und Fahrzeuge: `http://leitstelle:8080`
- Durchführung:
  1. Dashboard öffnen.
  2. Die Einheiten-Liste ansehen.
  3. Die Missionen und den Fortschritt prüfen.
- Erwartetes Ergebnis:
  - Die Rollen sind klar sichtbar.
  - Die Missionszustände sind gut lesbar.
  - Der Fortschritt ist im Dashboard verständlich.
- Tatsächliches Ergebnis:
  - Die Rollen sind sichtbar.
  - Die Missionszustände werden angezeigt.
  - Der Fortschritt ist gut lesbar.
- Artefakte / Nachweise: Browser-Dashboard
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

