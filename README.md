<p align="center">
  <img src="brands/icon@2x.png" width="160" alt="G.hn Adapter logo">
</p>

<h1 align="center">G.hn Adapter (MaxLinear) — Home Assistant Integration</h1>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <img src="https://img.shields.io/badge/iot__class-local__polling-blue.svg" alt="local polling">
</p>

Liest den Status von **MaxLinear-basierten G.hn-Adaptern** (G.hn-over-Coax, oft als
„MoCA"-/Koax-Netzwerkadapter verkauft, z. B. Zinwell **TGU-21**) lokal über deren
Web-GUI aus — komplett **ohne Cloud**.

Diese Adapter haben keine API, aber ihre Status-Seiten (`ghn.html` / `device.html`)
liefern alle Werte. Die Integration meldet sich an, parst die Seiten und stellt
Verbindungsqualität und Gerätezustand als Sensoren bereit.

## Funktionen

- 🔌 **Lokales Polling** (Standard 60 s), keine Cloud, keine zusätzlichen Python-Pakete
- 🔎 **Automatische Erkennung** per DHCP (Zinwell-OUI `00:05:9E*`)
- 🧩 **Config-Flow** — Host & Passwort in der UI, Mehrfach-Adapter unterstützt
- 📊 Pro Adapter:

| Entität | Beschreibung |
|---|---|
| `binary_sensor` **Verbindung** | erreichbar / eingeloggt (Device-Class `connectivity`) |
| `sensor` **Verbindungsgeschwindigkeit** | lokale G.hn-Rate (Mbit/s) |
| `sensor` **Schwächste Verbindung** | min. Tx/Rx über alle Knoten (Mbit/s); alle Peers als Attribut |
| `sensor` **Verbundene Knoten** | Anzahl der G.hn-Gegenstellen |
| `sensor` **Knotentyp** | `DOMAIN_MASTER` / `END_POINT` (+ Domain, Domain-ID, Profil, Secured, MAC) |
| `sensor` **CPU-Auslastung** | CPU-Last des Adapters (%) · Diagnose |
| `sensor` **Speicherauslastung** | RAM-Nutzung (%); frei/gesamt in kB als Attribut · Diagnose |
| `sensor` **Aktiv seit** | Boot-Zeitpunkt (Timestamp) — erkennt unerwartete Neustarts · Diagnose |
| `button` **Neustart** | löst einen Hardware-Reset (Reboot) aus — **kein** Factory-Reset |

> ℹ️ FW-/HW-Version stehen auf der Geräteseite (aus `device.html`).
> ℹ️ Ist ein Adapter beim HA-Start nicht erreichbar, wird die Integration trotzdem
> geladen und **Verbindung** meldet `off` — so kann eine Automation auch dann
> auslösen (bewusste Abweichung vom üblichen „Setup zurückstellen").
> ⚠️ Ein Neustart des **Domain-Masters** trennt kurzzeitig das gesamte Koax-Backbone.

## Installation (HACS)

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → URL dieses Repos, Kategorie **Integration**.
2. „G.hn Adapter (MaxLinear)" installieren.
3. **Home Assistant neu starten**.
4. **Einstellungen → Geräte & Dienste**: entweder erscheinen die Adapter automatisch
   unter *Entdeckt*, oder *Integration hinzufügen* → „G.hn Adapter (MaxLinear)".

### Manuelle Installation

`custom_components/ghn_maxlinear/` nach `<config>/custom_components/` kopieren und HA neu starten.

## Konfiguration

| Feld | Beschreibung |
|---|---|
| **Host / IP** | IP-Adresse des Adapters (z. B. `192.168.1.10`) |
| **Passwort** | das Web-GUI-Passwort |
| **Name** *(optional)* | Anzeigename, z. B. „Koax Keller" |

> ⚠️ **Passwort-Hinweis:** Die MaxLinear-GUI begrenzt das Passwort hart auf **20 Zeichen**.
> Längere Passwörter werden vom Gerät abgeschnitten — die Integration kürzt automatisch
> ebenfalls auf 20 Zeichen, damit der Login funktioniert.

Über **Konfigurieren** am Integrationseintrag lässt sich das **Abfrageintervall**
(15–3600 s, Standard 60 s) anpassen. Ändert sich IP oder Passwort, gehen
**Neu konfigurieren** bzw. der automatische **Neu-Anmelden**-Dialog — der Eintrag
muss dafür nicht gelöscht werden.

## Wie es funktioniert

Die Authentifizierung ist quell-IP-basiert (keine Cookies): Das Gerät merkt sich die
angemeldete Quell-IP, eine Sitzung überdauert also viele Abrufe. Ein Poll holt deshalb
zuerst `GET /ghn.html` und meldet sich nur dann neu an (`GET /` für den `.CSRFTOKEN`,
dann `POST /` mit `.PASSWORD`), wenn die Seite wieder das Login-Formular liefert.
Die Phy-Raten werden wie im GUI-JavaScript umgerechnet: `Mbit/s = floor(roh × 32 / 1000)`.

## Sicherheitshinweise

Beides folgt aus der Firmware der Adapter und lässt sich von der Integration nicht
beheben — man sollte es aber wissen:

- **Kein HTTPS.** Die GUI spricht nur HTTP, das Passwort geht im Klartext über das
  Netz. Die Integration überträgt es nur noch beim Sitzungsaufbau statt bei jedem
  Poll, aber sicher wird es dadurch nicht. G.hn-Adapter gehören nicht in ein
  Netzsegment mit fremden Geräten.
- **Quell-IP-Authentifizierung.** Solange die Sitzung des HA-Hosts steht, ist die
  komplette GUI für **jeden Prozess auf diesem Host** — und für alles, was hinter
  derselben Quell-IP steht (NAT, Container-Bridge) — ohne Passwort erreichbar,
  einschliesslich Neustart und Werksreset. Wer HA auf einem Mehrbenutzer-Host
  betreibt, sollte das einkalkulieren.

> ⚠️ Der **Neustart-Button** ist standardmässig aktiv. Ein Neustart des
> Domain-Masters trennt kurzzeitig das gesamte Koax-Backbone — wer ihn nicht
> braucht, deaktiviert die Entität in den Geräteeinstellungen.

## Geräte-Icon

Die Brand-Assets liegen direkt im Repo unter `custom_components/ghn_maxlinear/brand/`
(`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`). Ab **Home Assistant 2026.3**
liest HA diese lokalen Bilder automatisch über die Brands-Proxy-API – ein PR an
home-assistant/brands ist **nicht mehr nötig** (und wird dort nicht mehr akzeptiert).

## Haftungsausschluss

Kein offizielles Produkt von MaxLinear oder Zinwell. Reverse-engineert für die private
Web-GUI; eine Firmware-Änderung kann die Integration brechen.

## Lizenz

[MIT](LICENSE)
