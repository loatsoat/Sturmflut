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

- **Aufgabe / Meilenstein:** Aufgabe 1 - Leitstelle und Sensoren
- **Testtyp:** Funktional
- **Titel:** Anzeige von Personenerkennung im Protokoll
- **Ziel:** Prüfen, ob eine Personenerkennung im Verlauf und in der Historie sichtbar ist.
- **Vorbedingungen / Setup:**
  - System starten mit `docker compose up -d --build`
  - Eine Kameraeinheit ist verbunden
- **Durchführung:**
  1. Dashboard öffnen.
  2. Eine Personenerkennung über die Kamera auslösen.
  3. Die Incident-Historie im Dashboard ansehen.
- **Erwartetes Ergebnis:**
  - Der Vorfall wird gespeichert.
  - Der Wert für die Erkennung ist sichtbar.
  - Die Historie zeigt einen verständlichen Eintrag.
- **Tatsächliches Ergebnis:**
  - Der Vorfall wird gespeichert.
  - Der Confidence-Wert ist sichtbar.
  - Die Historie zeigt einen klaren Eintrag.
- **Artefakte / Nachweise:** Browser-Dashboard, Eintrag in `/history`
- **Bewertung:** PASS
- **Zugehöriger Commit / Versionsstand:** Lokaler Workspace nach dem letzten Rebuild

