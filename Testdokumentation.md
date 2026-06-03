# Testdokumentation 4.2

## Test 1

  - System starten mit `docker compose up -d --build`
  - Leitstelle läuft im Browser auf `http://127.0.0.1:8081/`
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

- **Aufgabe / Meilenstein:** Aufgabe 1 - Leitstelle und Dashboard
- **Testtyp:** Nicht-funktional
- **Titel:** Lesbarkeit der Inselkarte
- **Ziel:** Prüfen, ob die Karte im Browser gut lesbar ist und die wichtige Infrastruktur sichtbar ist.
- **Vorbedingungen / Setup:**
  - System starten mit `docker compose up -d --build`
  - Dashboard in einem normalen Browser öffnen
- **Durchführung:**
  1. Dashboard öffnen.
  2. Die komplette 20x20-Karte anschauen.
  3. Insel-Form, Sandfarben und Infrastruktursymbole prüfen.
- **Erwartetes Ergebnis:**
  - Die Karte ist sichtbar und gut lesbar.
  - Die Insel ist klar vom Wasser getrennt.
  - Die Infrastruktur ist leicht zu erkennen.
- **Tatsächliches Ergebnis:**
  - Die Karte ist gut lesbar.
  - Die Insel-Form ist sichtbar.
  - Die Infrastruktur ist klar markiert.
- **Artefakte / Nachweise:** Browser-Screenshot vom Dashboard
- **Bewertung:** PASS
- **Zugehöriger Commit / Versionsstand:** Lokaler Workspace nach dem letzten Rebuild

## Nicht-funktionaler Test
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
- Zugehöriger Commit / Versionsstand: v1