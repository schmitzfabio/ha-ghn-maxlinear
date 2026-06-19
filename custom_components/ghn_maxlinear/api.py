"""Client für die MaxLinear-G.hn-Web-GUI.

Die GUI hat keine API, aber die Seite ``ghn.html`` enthält alle Werte als
JavaScript-Variablen. Authentifizierung läuft quell-IP-basiert (keine Cookies):

1. ``GET  /``            – Login-Seite anfordern
2. ``POST /``            – Feld ``.PASSWORD`` (ohne ``OK``-Button!), Passwort
                           wird vom Gerät auf 20 Zeichen gekappt
3. ``GET  /ghn.html``    – Statusseite mit den JS-Variablen parsen

Umrechnung der Tabellenraten (wie im GUI-JavaScript):
``Mbps = floor(roh * 32 / 1000)``.
"""

from __future__ import annotations

import asyncio
import math
import re

import aiohttp

from .const import PASSWORD_MAXLEN


class GhnError(Exception):
    """Basisfehler."""


class GhnConnectionError(GhnError):
    """Adapter nicht erreichbar / unerwartete Antwort."""


class GhnAuthError(GhnError):
    """Login abgelehnt (falsches Passwort)."""


_RE_SPEED = re.compile(r"var\s+speed\s*=\s*(\d+)")
_RE_NODETYPE = re.compile(r'id="ghn_basic_nodetype">\s*([^<]+?)\s*<')
_RE_DOMAIN = re.compile(r'name="NODE\.GENERAL\.DOMAIN_NAME"\s+value="([^"]*)"')
_RE_SECURED = re.compile(r'var\s+secured\s*=\s*"([^"]*)"')
_RE_MYMAC = re.compile(r"var\s+mymac\s*=\s*'([^']*)'")
_RE_PCMASTR = re.compile(r'var\s+pcmastr\s*=\s*"([^"]*)"')
_RE_PCPTX = re.compile(r"var\s+pcptx\s*=\s*new\s+Array\(([^)]*)\)")
_RE_PCPRX = re.compile(r"var\s+pcprx\s*=\s*new\s+Array\(([^)]*)\)")

_TIMEOUT = aiohttp.ClientTimeout(total=10)


def _to_mbps(raw: int) -> int:
    return math.floor(raw * 32 / 1000)


def _parse_int_array(match: re.Match | None) -> list[int]:
    if not match:
        return []
    out: list[int] = []
    for part in match.group(1).split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


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

    async def _login(self) -> None:
        try:
            await self._session.get(f"{self._base}/", timeout=_TIMEOUT)
            await self._session.post(
                f"{self._base}/",
                data={
                    ".CSRFTOKEN": "",
                    ".REDIRECT": "/",
                    ".PASSWORD": self._password,
                },
                timeout=_TIMEOUT,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GhnConnectionError(f"Login-Request fehlgeschlagen: {err}") from err

    async def async_get_data(self) -> dict:
        """Login + ghn.html holen und parsen."""
        await self._login()
        try:
            resp = await self._session.get(f"{self._base}/ghn.html", timeout=_TIMEOUT)
            text = await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GhnConnectionError(f"Statusabruf fehlgeschlagen: {err}") from err

        if resp.status == 403 or "AUTH_FORM" in text or "password protected" in text.lower():
            raise GhnAuthError("Login abgelehnt – Passwort prüfen")
        if resp.status != 200 or "pcmastr" not in text:
            raise GhnConnectionError(f"Unerwartete Antwort (HTTP {resp.status})")

        return self._parse(text)

    @staticmethod
    def _parse(text: str) -> dict:
        m_mymac = _RE_MYMAC.search(text)
        mymac = (m_mymac.group(1).lower() if m_mymac else "")

        macs: list[str] = []
        m_macs = _RE_PCMASTR.search(text)
        if m_macs:
            macs = [x.strip().lower() for x in m_macs.group(1).split(",")]

        ptx = _parse_int_array(_RE_PCPTX.search(text))
        prx = _parse_int_array(_RE_PCPRX.search(text))

        peers: list[dict] = []
        for i, mac in enumerate(macs):
            if i == 0:  # erstes Element ist immer 00:00:00:00:00:00
                continue
            if mac in ("", mymac, "00:00:00:00:00:00"):
                continue
            peers.append(
                {
                    "mac": mac,
                    "tx_mbps": _to_mbps(ptx[i]) if i < len(ptx) else None,
                    "rx_mbps": _to_mbps(prx[i]) if i < len(prx) else None,
                }
            )

        rates = [
            v for p in peers for v in (p["tx_mbps"], p["rx_mbps"]) if v is not None
        ]

        m_speed = _RE_SPEED.search(text)
        m_node = _RE_NODETYPE.search(text)
        m_dom = _RE_DOMAIN.search(text)
        m_sec = _RE_SECURED.search(text)

        return {
            "mac": mymac,
            "node_type": m_node.group(1).strip() if m_node else None,
            "domain": m_dom.group(1) if m_dom else None,
            "secured": (m_sec.group(1) == "YES") if m_sec else None,
            "speed_mbps": int(m_speed.group(1)) if m_speed else None,
            "peers": peers,
            "peer_count": len(peers),
            "min_rate_mbps": min(rates) if rates else None,
        }
