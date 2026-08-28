# G.hn Adapter (MaxLinear)

Lokale Integration für MaxLinear-basierte **G.hn-Koax-Adapter** (z. B. Zinwell TGU-21).
Liest Verbindungsqualität (Geschwindigkeit, schwächster Link, Knotenanzahl, Knotentyp)
sowie Gerätezustand (CPU, RAM, Uptime, FW-/HW-Version) direkt aus der Web-GUI — ohne Cloud.

- Automatische DHCP-Erkennung
- Config-Flow (Host + Passwort in der UI)
- Mehrere Adapter parallel
- Neustart-Button (Hardware-Reset, kein Factory-Reset)
- Einstellbares Abfrageintervall, Neu-Anmelden und Neu-Konfigurieren

Benötigt Home Assistant **2025.1** oder neuer.

> ⚠️ Die Web-GUI der Adapter kann kein HTTPS und authentifiziert über die
> Quell-IP — Details im README unter „Sicherheitshinweise".

Nach der Installation **Home Assistant neu starten** und die Adapter unter
*Einstellungen → Geräte & Dienste* hinzufügen.
