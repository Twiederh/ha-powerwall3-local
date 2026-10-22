# Powerwall 3 Local

Home-Assistant-Integration, die eine **Tesla Powerwall 3 lokal** über [pypowerwall](https://github.com/jasonacox/pypowerwall) ausliest – ohne Cloud. Schwerpunkt sind die **PV-Strings des integrierten Wechselrichters**: Leistung, Spannung, Strom und daraus berechnete **Energie pro String und gesamt** (heute / Lebensdauer).

Damit lässt sich der Ertrag der direkt an der Powerwall 3 angeschlossenen Module getrennt von AC-gekoppelten Wechselrichtern (SMA, SolarEdge, …) erfassen – z. B. für eine eigene PVOutput-Anlage.

> Status: 0.1.0 – erste Version, an einer echten Powerwall 3 in Betrieb.

## Sensoren

| Sensor | Einheit | Hinweis |
|---|---|---|
| String X Leistung / Spannung / Strom | W / V / A | pro PV-Eingang (A–F) |
| String X Status | – | standardmäßig deaktiviert (`Pv_Active`, `Pv_Active_Parallel`, `Pv_Standby`) |
| String X Energie heute / gesamt | kWh | integriert aus der Stringleistung |
| **PV-Leistung** | W | Summe aller Strings = Ausgang des integrierten Wechselrichters |
| **PV-Energie heute** | kWh | setzt um Mitternacht (lokale Zeit) auf 0 zurück |
| **PV-Energie gesamt** | kWh | Lebensdauerzähler, für das Energie-Dashboard |
| Solarleistung Standort | W | alles, was das Gateway als Solar misst (inkl. AC-gekoppelter Anlagen mit CT) |
| Batteriestand, Batterie-, Netz-, Hausleistung, Netzstatus | %, W | Standortwerte |

Die Energiezähler werden per Trapezregel aus den Leistungswerten berechnet und in `.storage` gesichert, sie überstehen also Neustarts. Ist die Powerwall länger als 5 Minuten nicht erreichbar, wird für diese Lücke **keine** Energie hochgerechnet. Die Energie-Sensoren bleiben bei Verbindungsabbrüchen verfügbar (kein Springen auf „nicht verfügbar“, wichtig für PVOutput-Uploads).

## Netzwerk-Voraussetzungen

Die Powerwall 3 hat **keine normale lokale API** im Heimnetz. Es gibt zwei Wege:

### A) Kabel-LAN, v1r-Modus (empfohlen für Dauerbetrieb)

- Der Ethernet-Port am Tesla Energy Gateway liegt in einem **eigenen Vendor-Subnetz** (typisch `10.42.1.0/24` oder `10.45.1.0/24`), nicht in deinem Heimnetz.
- Home Assistant braucht eine Layer-2-Verbindung dorthin (eigene Netzwerkkarte, VLAN am Switch oder Bridge).
- Die Powerwall hat dort **keine statische IP** – du brauchst einen **DHCP-Server** in diesem Subnetz (z. B. ein eigenes VLAN mit DHCP auf dem Router).
- Einmalig muss ein **RSA-Schlüssel** bei der Powerwall registriert werden (siehe unten).

### B) Powerwall-WLAN (TEDAPI)

- Der HA-Host verbindet sich mit dem WLAN-Accesspoint der Powerwall (`TEG-xxx`), Host `192.168.91.1`.
- Routing aus dem Heimnetz zu `192.168.91.1` wird seit Firmware 25.10 von Tesla blockiert.
- Laut pypowerwall-Community klappt es bei manchen PW3 auch mit der **Heimnetz-IP der Powerwall** als Host (ebenfalls mit Gateway-Passwort) – einen Versuch wert.

## RSA-Schlüssel registrieren (nur v1r)

Die Registrierung läuft einmalig auf einem beliebigen Rechner mit Python (nicht in HA) über die Tesla-Cloud. Der Rechner muss dafür **nicht** mit der Powerwall verbunden sein.

### 1. Vorbereiten

```bash
mkdir ~/powerwall-key && cd ~/powerwall-key
python3 -m venv venv
source venv/bin/activate
pip install pypowerwall
```

Ein eigener Ordner ist sinnvoll, weil das Skript den Schlüssel im aktuellen Verzeichnis ablegt.

> **macOS – `CERTIFICATE_VERIFY_FAILED`:** Python vom python.org-Installer bringt keine Root-Zertifikate mit. Entweder einmalig `open "/Applications/Python 3.13/Install Certificates.command"` ausführen (Version anpassen) oder für die aktuelle Sitzung `export SSL_CERT_FILE=$(python -m certifi)` setzen. Die Zertifikatsprüfung bitte nicht abschalten.

### 2. Registrieren – mit der Fleet API (Option 2)

```bash
python -m pypowerwall register
```

Option 1 (Owner API) wird von Tesla inzwischen oft mit `Failed to get products (403) … forbidden` abgelehnt. Zuverlässig ist **Option 2 mit deiner eigenen Fleet-API-App** (dieselbe wie für die Tesla-Fleet-Integration):

- Methode **`2`** wählen
- **Client ID**, **Client Secret** und die in der App eingetragene **Redirect URI** angeben (z. B. `https://my.home-assistant.io/redirect/oauth` – Zeichen für Zeichen identisch, ohne Slash am Ende)
- Region **`2` (Europe)** bzw. deine Region
- Die App braucht die Scopes **Energy Product Information** und **Energy Product Commands/Settings** (`energy_device_data`, `energy_cmds`)
- Den angezeigten Link im Browser öffnen und bei Tesla anmelden. Danach landest du auf der Redirect-Seite (eine Fehlermeldung dort ist normal). Die **komplette URL aus der Adresszeile** (enthält `?code=…`) zügig ins Terminal kopieren – der Code ist nur wenige Minuten gültig.
- Energy Site auswählen; der Schlüssel wird registriert.

Die Energy-Endpunkte der Fleet API sind kostenlos.

### 3. Physische Bestätigung (falls verlangt)

Erscheint „Key verified automatically via cloud“, bist du fertig. Sonst fordert das Skript eine Bestätigung an der Powerwall:

- **Innerhalb von ca. 10 Minuten** den **On/Off-Schalter der Powerwall 3** (links am Gerät unter der roten Rapid-Shutdown-Klappe) **ca. 15 Sekunden ausschalten**, dann wieder ein. Ein kurzes Antippen wird ignoriert; nicht so lange aus lassen, bis das Gerät komplett herunterfährt.
- Danach im Terminal Enter drücken – am Ende sollte „Key is VERIFIED“ stehen.
- Meldet das Skript „State 2“, war das Zeitfenster zu: Befehl einfach erneut ausführen, der vorhandene Schlüssel wird wiederverwendet.

### 4. Schlüssel nach Home Assistant kopieren

`tedapi_rsa_private.pem` nach `/config/tedapi_rsa_private.pem` kopieren (Samba-Freigabe, Studio Code Server o. Ä.). Dieser Pfad ist in der Integration vorausgefüllt.

Die Datei ist wie ein Passwort zu behandeln: Wer sie hat, kann die Powerwall lokal steuern. Nicht in Git-Repos oder Backups ohne Verschlüsselung legen.

### Test vorab (optional)

```bash
python -m pypowerwall get -v1r -host 10.42.1.x -gw_pwd DEIN_QR_PASSWORT -rsa_key_path ./tedapi_rsa_private.pem
```

Zeigt das Batteriestand und Solarleistung, funktioniert auch die Integration.

## Installation

**HACS:** Benutzerdefiniertes Repository `https://github.com/Twiederh/ha-powerwall3-local` (Typ Integration) hinzufügen, installieren, HA neu starten.

**Manuell:** Ordner `custom_components/powerwall3_local` nach `/config/custom_components/` kopieren, HA neu starten.

Dann: *Einstellungen → Geräte & Dienste → Integration hinzufügen → Powerwall 3 Local*

1. Verbindungsart wählen (Kabel-LAN v1r oder WLAN)
2. Host, **vollständiges Gateway-Passwort** (QR-Aufkleber auf der Powerwall 3) und bei v1r den Schlüsselpfad eintragen

Das Abfrageintervall (Standard 10 s) lässt sich unter *Konfigurieren* ändern.

## Nutzung mit PVOutput

Für eine eigene PVOutput-Anlage der Module an der Powerwall 3 den Sensor **„PV-Energie heute“** (und optional „PV-Leistung“) verwenden.

### Hinweis zu parallel verschalteten Strings

Werden zwei Strings parallel auf einen MPPT gelegt, meldet die Powerwall den zweiten Eingang als `Pv_Active_Parallel`. Prüfe in den ersten Tagen, ob die Summe („PV-Leistung“) zu den Werten in der Tesla-App passt. Falls ein paralleler Eingang dieselben Messwerte doppelt meldet, bitte ein Issue aufmachen – dann wird die Summenbildung angepasst.

## Danke

Basiert auf der Reverse-Engineering-Arbeit von Jason Cox und der [pypowerwall](https://github.com/jasonacox/pypowerwall)-Community. Nicht mit Tesla verbunden.
