# Anforderungsanalyse – Sturmflut Nordsee

**Gruppe:** Ho Quang Minh Phan (1123173), Bao Chau Nguyen (1119742)  
**Semester:** SS2026  
**Modul:** Verteilte Systeme

---

## 1. Systemübersicht

Ein verteiltes Katastrophenmanagementsystem für eine fiktive Nordseeinsel
nach einer Sturmflut. Rettungs-, Reparatur- und Versorgungsfahrzeuge
werden koordiniert. Alle Teilprozesse laufen in eigenen Docker-Containern.

---

## 2. Komponenten

| Komponente      | Beschreibung                                              | Aufgabe |
|-----------------|-----------------------------------------------------------|---------|
| Leitstelle      | Zentrale Verwaltung, REST-API, Inselkarte (20x20 Grid)    | 1       |
| Dashboard       | Browserbasierte Anzeige der Karte und des Status          | 1       |
| Sensor-Gateway  | Empfängt Rohdaten von Sensoren, leitet Vorfälle weiter    | 1       |
| Kamera A/B      | Erkennt Personen, blockierte Wege, meldet Vorfälle        | 1       |
| Drohne          | Fliegt über Wasser, inspiziert schwer erreichbare Orte    | 2       |
| Reparatur-Rover | Fährt auf Land, repariert Strukturschäden                 | 2       |
| Versorgungs-Rover | Liefert Material bei niedrigem Lagerbestand             | 2       |
| MQTT-Broker     | Entkoppelte Ereignisverarbeitung (z.B. Mosquitto)         | 3       |
| Ladestation     | Knappe Ressource, koordiniert via Ricart/Agrawala         | 4       |

---

## 3. Funktionale Anforderungen

### Aufgabe 1 – REST via TCP-Sockets
- [ ] Leitstelle implementiert HTTP-Server über rohe TCP-Sockets
- [ ] Unterstützte Methoden: GET, POST (andere → 405 Method Not Allowed)
- [ ] Endpunkte:
  - `POST /unit` – Fahrzeug/Sensor registrieren
  - `POST /incident` – Vorfall melden
  - `GET /map` – Inselkarte abfragen
  - `GET /status` – Gesamtzustand abfragen
- [ ] Inselkarte: mindestens 20x20 Felder (Wasser / Land)
- [ ] Feste Infrastruktur auf der Karte: Brücke, Hafen, Ladestation, Depot
- [ ] Mindestens 2 Sensortypen mit Rohmesswerten:
  - `water_level_cm` – Pegelstand
  - `person_confidence` – Personenerkennung
- [ ] Mindestens 2 Kameras melden Vorfälle aus Schwellwertverletzungen
- [ ] Dashboard im Browser renderbar (Chrome/Firefox)

### Aufgabe 2 – RPC
- [ ] Mindestens 2 Fahrzeugrollen (Drohne, Rover)
- [ ] Drohnen dürfen über Wasser fliegen, Bodenfahrzeuge nicht
- [ ] IDL-Definition der RPC-Schnittstelle (gRPC oder Thrift)
- [ ] Leitstelle weist Einsätze per RPC zu
- [ ] Fahrzeugzustände: IDLE, ASSIGNED, BUSY, ERROR
- [ ] Rollenzuordnung nach Ereignistyp:
  - Personenerkennung → Drohne
  - Strukturschaden → Reparatur-Rover
  - Niedriger Lagerbestand → Versorgungs-Rover
- [ ] Rückmeldung: Bestätigung, Fortschritt, Abschluss/Fehler

### Aufgabe 3 – MQTT
- [ ] MQTT-Broker läuft als eigener Container
- [ ] Kameras und Sensoren publizieren Ereignisse
- [ ] Fahrzeuge publizieren Telemetrie (Position, Fortschritt, Fehler)
- [ ] Leitstelle behandelt Duplikate und veraltete Nachrichten
- [ ] Topic-Struktur und QoS-Stufen definiert und dokumentiert
- [ ] Nachrichtenformat JSON, dokumentiert
- [ ] GET /map und GET /status basieren auf MQTT-Daten
- [ ] Fehlerszenarien getestet: Broker-Ausfall, Publisher-Neustart

### Aufgabe 4 – Ricart/Agrawala
- [ ] Mindestens 3 Fahrzeuge am gegenseitigen Ausschluss beteiligt
- [ ] Koordination über REQUEST/REPLY-Nachrichten
- [ ] Totalordnung über logische Zeit (Lamport-Uhr)
- [ ] Leitstelle beobachtet nur, vergibt nicht mehr zentral
- [ ] Safety nachgewiesen: nie zwei Fahrzeuge gleichzeitig in kritischer Sektion
- [ ] Liveness nachgewiesen: wartende Fahrzeuge kommen weiter
- [ ] Fehlerbetrachtung: Nachrichtenausfall, Prozessabsturz

---

## 4. Nicht-funktionale Anforderungen

| Anforderung       | Beschreibung                                              |
|-------------------|-----------------------------------------------------------|
| Containerisierung | Jede Komponente läuft in eigenem Docker-Container         |
| Build-Tool        | Makefile mit Targets: up, down, build, logs, clean        |
| Reproduzierbarkeit| System startet vollständig mit `make up`                  |
| Sprache           | Keine Vorgabe, Kombination erlaubt                        |
| Repository        | GitLab H-DA, Lösungen im Main-Branch                      |
| Dokumentation     | Testprotokolle versioniert im Repository                  |

---

## 5. Systemgrenzen

- Kein echter Sensor-Hardware-Zugriff – alle Sensoren sind simuliert
- Kein eigener MQTT-Broker programmiert – fertiger Broker (z.B. Mosquitto)
- HTTP-Server und Sockets in Aufgabe 1 ohne externe Frameworks
- Pi-Lab (ARM): Container müssen auf ARM-Architektur lauffähig sein