[English documentation](README.md)

# Natural Shutter

<p align="center">
  <img
    src="docs/banner.png"
    alt="Banner von Natural Shutter"
    width="100%"
    style="display: block; width: 100%; background-color: #ffffff;"
  >
</p>

Natural Shutter ergänzt deine vorhandenen Home-Assistant-Rollläden um eine
gespeicherte Ziel-Position und einen Fahrpuffer. Unterstützt werden Covers mit
Positionsbefehlen, beispielsweise aus Homematic IP, Shelly und anderen Integrationen.

## Funktionen

- Jeden Rollladen manuell über die HA-Oberfläche hinzufügen; keine automatische Aufnahme.
- Zwei unabhängige Schieberegler pro Rollladen: **Ziel-Position** und **Puffer**.
- Zwei numerische Verlaufssensoren: **Ziel-Position Verlauf** und **Puffer Verlauf**.
- Bei Start und Reload übernimmt das Ziel die Istposition ohne Fahrbefehl;
  der Puffer bleibt erhalten.
- Deutsche und englische Einrichtung, Entitätsnamen und Aktionsfehlermeldungen.
- Vorhandene Cover-Entitäten und Herstellerintegrationen werden weiter verwendet.
- Die Verfügbarkeit des Zielreglers folgt dem Quell-Cover; Wiederverbindung ohne Fahrt.
- Alle hinzugefügten Rollläden stehen unter **Natural Shutter** im Reiter **Integrationen**.
- Gegenseitige Navigation über **Verknüpfte Geräte** zwischen virtuellem Gerät und Aktor.

## Ziel-Position und Puffer

**Ziel-Position:** 0 % bedeutet vollständig geöffnet, 100 % vollständig geschlossen.
Bis zum nächsten Laden der Integration hält der Wert deine letzte Einstellung fest.
Bedienungen über Wandtaster,
Hersteller-App, Alexa, das ursprüngliche HA-Cover oder andere Automationen können
den Rollladen bewegen, ohne diese gespeicherte Ziel-Position zu ändern. Erst beim
erneuten Laden erfolgt wieder der Abgleich mit der Istposition.

**Puffer:** der Mindestabstand in **Prozentpunkten** zwischen Istposition und
gewünschter Position. Eine Fahrt wird nur ausgelöst, wenn du das Ziel ausdrücklich
änderst, der Rollladen davon abweicht und der Abstand mindestens dem Puffer
entspricht. Bei Puffer 0 sendet jede Zieländerung mit abweichender Istposition einen
Befehl. Die Änderung des Puffers selbst löst niemals eine Fahrt aus.

Beide Regler reichen von 0 bis 100 %, Schrittweite 1. Dezimale Aktionswerte werden
auf ganze Prozent gerundet, bei einer Hälfte aufwärts. Ungültige Werte und Werte
außerhalb des Bereichs werden abgelehnt.

### Beispiel

Ändere das Ziel auf **70 %** bei **10 %** Puffer. Natural Shutter fordert am
ursprünglichen HA-Cover **30 %** an. Dessen Skala lautet 0 % geschlossen und
100 % geöffnet.

| Aktuelle HA-Position | Abstand | Ergebnis |
| --- | --- | --- |
| 45 % | 15 Punkte | Auf 30 % fahren |
| 40 % | 10 Punkte | Auf 30 % fahren |
| 35 % | 5 Punkte | Ziel speichern; stehen bleiben |
| 30 % | 0 Punkte | Stehen bleiben |
| 20 % | 10 Punkte | Auf 30 % fahren |
| 15 % | 15 Punkte | Auf 30 % fahren |

Dieselbe Regel gilt für vollständig geöffnete und geschlossene Ziele.

## Installation

Voraussetzung: **Home Assistant ab 2026.8.0** und ein Cover, das absolute
Positionsbefehle unterstützt. Die Geräteverknüpfung verwendet die seit HA 2026.8
getrennten Geräte verschiedener Integrationen. Ältere Versionen werden vor Änderungen
an Einstellungen oder Geräten abgelehnt. Die automatisierten Tests verwenden HA
2026.9.4; die Registry-APIs der Mindestversion wurden geprüft, ihr vollständiger
Laufzeitbetrieb jedoch noch nicht. Das mitgelieferte Integrationsicon wird automatisch
angezeigt.

### HACS als benutzerdefiniertes Repository — nach Veröffentlichung

Das Projekt ist derzeit lokal und unveröffentlicht. Das geplante Repository heißt
[jan-brinkmann/ha-natural-shutter](https://github.com/jan-brinkmann/ha-natural-shutter).
**Das Repository existiert noch nicht.** Seine Adresse ist bereits in den
Integrationsmetadaten eingetragen; die folgenden HACS-Schritte gelten nach der
Veröffentlichung.

1. Öffne **HACS → ⋮ → Benutzerdefinierte Repositories**.
2. Trage `https://github.com/jan-brinkmann/ha-natural-shutter` ein und wähle **Integration**.
3. Lade **Natural Shutter** herunter und starte Home Assistant vollständig neu.
4. Folge der Einrichtung unten.

Die [Veröffentlichungsliste](docs/PUBLISHING.md) nennt die ausstehende
Repository-Einrichtung und Validierung. Eine erfolgreiche HACS-Installation oder
offizielle Aufnahme wird nicht behauptet.

### Manuelle Installation — bereits möglich

1. Kopiere den vollständigen Ordner `custom_components/natural_shutter` nach
   `<Konfigurationsverzeichnis>/custom_components/natural_shutter`.
   Unter Home Assistant OS beginnt der Pfad üblicherweise mit `/config`.
2. Prüfe, dass `manifest.json` direkt in diesem Ordner liegt.
3. Starte Home Assistant vollständig neu.

## Einrichtung und tägliche Verwendung

1. Öffne **Einstellungen → Geräte & Dienste → Integration hinzufügen → Natural Shutter**.
2. Wähle ein vorhandenes Cover. Vergib optional einen gut unterscheidbaren Namen.
3. Wiederhole die Einrichtung für jeden weiteren Rollladen. Jeder Eintrag erhält
   ein eigenes virtuelles Gerät mit vier Entitäten; doppelte Quellen werden abgelehnt.

Alle Einträge findest du gemeinsam unter **Einstellungen → Geräte & Dienste →
Integrationen → Natural Shutter**. Auf der Seite eines virtuellen Geräts führt
**Verknüpfte Geräte** zum Aktor aus Shelly, Homematic IP oder einer anderen
Quellintegration. Auf der Aktorseite erscheint umgekehrt das Natural-Shutter-Gerät.
Dafür werden ausschließlich Kennungen und Verbindungen am virtuellen Gerät ergänzt.
Metadaten, Integrationszugehörigkeit und Entitäten des Aktors bleiben unverändert.
Die Verknüpfung folgt einer geänderten Gerätezuordnung und einer Neukonfiguration
ohne Fahrt. Nach dem Integrationsupdate und einem vollständigen HA-Neustart erhalten
auch bestehende Einträge die Verknüpfung; erneutes Hinzufügen ist nicht erforderlich.

Hat das Quell-Cover kein registriertes Gerät, gibt es kein Aktorgerät zum Verknüpfen.
Bei einem Cover als untergeordnetem Kanalgerät führt der Link zum übergeordneten
Aktor: Die HA-Liste **Verknüpfte Geräte** unterstützt Hauptgeräte.

Der Puffer beginnt bei **0 %**. Bei jedem Laden der Integration, auch bei Start und
Reload, wird die Ziel-Position auf **100 minus die aktuelle HA-Position des
Quell-Covers** gesetzt und auf ganze Prozent gerundet. Der Wert wird gespeichert,
ohne einen Fahrbefehl zu senden, unabhängig vom Puffer. Der gespeicherte Puffer
bleibt erhalten.

Fehlt beim Laden eine gültige aktuelle Position, bleibt das gespeicherte Ziel
erhalten. Bei einer neuen Zuordnung dient die bei der Auswahl erfasste Position
als Ersatzwert, andernfalls 0 %. Spätere Positionsmeldungen und Wiederverbindungen
ändern das Ziel nicht; dafür ist ein erneutes Laden oder eine ausdrückliche
Regleränderung erforderlich.

Bediene die Regler auf der Geräteseite oder in einer Standard-Dashboard-Karte.
Automationen können `number.set_value` für den Zielregler aufrufen. Die genauen
Entity-IDs findest du auf der Geräteseite; sie hängen von Sprache und Namen ab.

```yaml
service: number.set_value
target:
  entity_id: number.wohnzimmer_ziel_position  # Durch deine Entity-ID ersetzen.
data:
  value: 70
```

Über **Neu konfigurieren** im Menü des Eintrags kannst du den Namen ändern oder
eine fehlende Quelle ausdrücklich ersetzen. Dabei wird der Eintrag neu geladen:
Der Puffer bleibt erhalten, das Ziel übernimmt eine gültige aktuelle Quellposition
ohne Fahrt. Ein Options Flow ist nicht erforderlich, da die beiden
Betriebseinstellungen direkt als Regler vorliegen.

Siehe [Standard-Dashboard-Beispiele](examples/dashboard.yaml),
[lokale Testanleitung](docs/TESTING.md) und [Architektur auf Englisch](ARCHITECTURE.md).

## Verhalten und Grenzen

- Installation, Start, Reload, Wiederherstellung, Wiederverbindung, externe
  Bewegungen, Sensoraktualisierungen, Pufferänderungen und das erneute Setzen
  desselben normalisierten Zielwerts lösen keine Fahrt aus. Es gibt keine
  automatische Nachregelung auf das gespeicherte Ziel.
- Der Zielregler ist nicht verfügbar, wenn die Quelle fehlt, unbekannt, nicht
  verfügbar, deaktiviert oder nur als wiederhergestellter Platzhalter vorhanden ist.
  Ziel-Aktionen werden dann von HA übersprungen, ohne einen neuen Wert zu speichern.
  Bei Wiederverbindung erscheint das gespeicherte Ziel ohne Fahrt oder erneuten
  Positionsabgleich. Puffer und Verlaufssensoren bleiben verfügbar.
- Fällt die Quelle während des Speicherns einer bereits angenommenen Zieländerung
  aus oder liefert sie eine ungültige Istposition, bleibt das neue Ziel gespeichert.
  Die übersprungene Aktion wird in Oberfläche/Aktionsverlauf und HA-Protokoll
  gemeldet. Nichts wird vorgemerkt. Auch fehlgeschlagene Cover-Aktionen behalten das
  Ziel und werden nicht automatisch wiederholt. Für einen neuen Versuch musst du
  bei verfügbarer Quelle ausdrücklich einen anderen Zielwert wählen.
- Quellen mit stabiler Registry-Identität können umbenannt werden. Ohne diese
  Identität ist nach einer Entity-ID-Umbenennung eine manuelle Neukonfiguration
  erforderlich.
- Die Verlaufssensoren zeigen Einstellungen, auch bei unterdrückten Fahrten.
  Verfügbarkeit und Aufbewahrungsdauer des Verlaufs hängen von **Recorder** und
  dessen Filtern ab. Ein eigenes Archiv oder Langzeitstatistiken werden nicht erstellt.
- Kalibrierung, Fahrtrichtung, Fahrfortschritt und Gerätekommunikation liegen bei
  der Quellintegration. Tests mit echter Hardware wurden nicht ausgeführt.

## Entfernen

Entferne den gewünschten Eintrag unter **Einstellungen → Geräte & Dienste →
Natural Shutter**. Nur seine vier Entitäten und gespeicherten Einstellungen werden
entfernt. Das Quell-Cover und andere Zuordnungen bleiben erhalten. Recorder-Verlauf
unterliegt weiterhin dessen Aufbewahrung. Nachdem alle Einträge entfernt wurden,
kannst du die Integration über HACS deinstallieren oder ihren Ordner manuell löschen
und Home Assistant neu starten.

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
Copyright (c) 2026 Jan Brinkmann and contributors.
