"""Client für die MaxLinear-G.hn-Web-GUI.

Die GUI hat keine API, aber die Seiten ``ghn.html`` / ``device.html`` enthalten
alle Werte als JavaScript-Variablen bzw. in HTML-Elementen mit fester ``id``.
Authentifizierung läuft quell-IP-basiert (keine Cookies): das Gerät merkt
sich die eingeloggte Quell-IP, eine einmal aufgebaute Sitzung überdauert
also viele Abrufe. Deshalb wird pro Poll NICHT neu eingeloggt, sondern nur,
wenn die Statusseite wieder das Login-Formular liefert:

1. ``GET  /ghn.html``    – Statusseite (Link-Raten, CPU/RAM, DOD, Profil)
2. nur falls nötig: ``GET /`` (liefert ``.CSRFTOKEN``) und ``POST /`` mit
   ``.CSRFTOKEN`` + ``.PASSWORD`` (ohne ``OK``-Button!); das Passwort wird
   vom Gerät auf 20 Zeichen gekappt. Danach Schritt 1 erneut.
3. ``GET  /device.html`` – Geräteseite (Uptime, FW-/HW-Version)

Das halbiert die Requests pro Poll und überträgt das Passwort nur noch,
wenn die Sitzung tatsächlich abgelaufen ist (die GUI kann kein HTTPS).

Das Parsen der Seiten liegt in :mod:`.parser` – dieses Modul macht nur
Transport und Fehlerübersetzung.

Ein Neustart läuft über dasselbe Formular-Muster wie der Login: ``POST /`` mit
``.SYSTEM.GENERAL.HW_RESET=1`` (Formular ``HW_RESET_FORM`` auf ``advanced.html``).
Das ist ein reiner Reboot – der destruktive Factory-Reset wird bewusst NICHT
implementiert.
"""

from __future__ import annotations

import asyncio

import aiohttp

from .const import PASSWORD_MAXLEN
from .parser import (
    is_login_page,
    looks_like_status_page,
    parse_csrf_token,
    parse_device,
    parse_status,
)


class GhnError(Exception):
    """Basisfehler."""


class GhnConnectionError(GhnError):
    """Adapter nicht erreichbar / unerwartete Antwort."""


class GhnAuthError(GhnError):
    """Login abgelehnt (falsches Passwort)."""


_TIMEOUT = aiohttp.ClientTimeout(total=10)


class GhnClient:
    """Liest Status von einem MaxLinear-G.hn-Adapter."""

    def __init__(
        self, host: str, password: str, session: aiohttp.ClientSession
    ) -> None:
        self._host = host.strip()
        # GUI kappt auf 20 Zeichen – sonst wird der Login abgelehnt.
        self._password = (password or "")[:PASSWORD_MAXLEN]
        self._session = session
        self._base = f"http://{self._host}"

    async def _get(self, path: str) -> tuple[int, str]:
        """GET auf den Adapter; Dekodierfehler brechen den Abruf nicht ab."""
        try:
            resp = await self._session.get(f"{self._base}{path}", timeout=_TIMEOUT)
            # Die GUI deklariert kein Charset – errors="replace" verhindert,
            # dass ein einzelnes Fremdbyte den kompletten Poll killt.
            return resp.status, await resp.text(errors="replace")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GhnConnectionError(f"GET {path} fehlgeschlagen: {err}") from err

    async def _login(self) -> None:
        """Sitzung für die eigene Quell-IP aufbauen."""
        _, page = await self._get("/")
        try:
            resp = await self._session.post(
                f"{self._base}/",
                data={
                    ".CSRFTOKEN": parse_csrf_token(page),
                    ".REDIRECT": "/",
                    ".PASSWORD": self._password,
                },
                timeout=_TIMEOUT,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GhnConnectionError(f"Login-Request fehlgeschlagen: {err}") from err

        if resp.status in (401, 403):
            raise GhnAuthError("Login abgelehnt – Passwort prüfen")
        if resp.status >= 400:
            raise GhnConnectionError(f"Login fehlgeschlagen (HTTP {resp.status})")

    async def async_get_data(self) -> dict:
        """ghn.html (+ device.html) holen und parsen, bei Bedarf vorher Login."""
        status, text = await self._get("/ghn.html")

        # Sitzung abgelaufen (oder noch keine) -> einloggen und einmal wiederholen.
        if (
            status in (401, 403)
            or is_login_page(text)
            or not looks_like_status_page(text)
        ):
            await self._login()
            status, text = await self._get("/ghn.html")

        if status in (401, 403) or is_login_page(text):
            raise GhnAuthError("Login abgelehnt – Passwort prüfen")
        if status != 200 or not looks_like_status_page(text):
            raise GhnConnectionError(f"Unerwartete Antwort (HTTP {status})")

        data = parse_status(text)

        # device.html ist optional – schlägt der Abruf fehl, bleiben Uptime/FW/HW
        # None, der Rest der Sensoren funktioniert trotzdem weiter.
        try:
            dstatus, dtext = await self._get("/device.html")
        except GhnConnectionError:
            pass
        else:
            if dstatus == 200 and not is_login_page(dtext):
                data.update(parse_device(dtext))

        return data

    async def async_reboot(self) -> None:
        """Hardware-Reset (Neustart) auslösen – kein Factory-Reset.

        Nutzt dasselbe quell-IP-Auth-Muster wie der Login. Der Adapter kappt die
        Antwort beim Neustart oft mittendrin – eine Connection-/Timeout-Ausnahme
        NACH dem abgesetzten POST gilt daher als Erfolg.
        """
        await self._login()
        try:
            await self._session.post(
                f"{self._base}/",
                data={
                    ".CSRFTOKEN": "",
                    ".REDIRECT": "reset.html",
                    ".SYSTEM.GENERAL.HW_RESET": "1",
                },
                timeout=_TIMEOUT,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError):
            # Erwartet: das Gerät startet neu und antwortet nicht mehr.
            pass
