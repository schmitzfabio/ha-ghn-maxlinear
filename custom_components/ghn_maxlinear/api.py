"""Client für die MaxLinear-G.hn-Web-GUI.

Die GUI hat keine API, aber die Seiten ``ghn.html`` / ``device.html`` enthalten
alle Werte als JavaScript-Variablen bzw. in HTML-Elementen mit fester ``id``.
Authentifizierung läuft quell-IP-basiert (keine Cookies):

1. ``GET  /``            – Login-Seite anfordern
2. ``POST /``            – Feld ``.PASSWORD`` (ohne ``OK``-Button!), Passwort
                           wird vom Gerät auf 20 Zeichen gekappt
3. ``GET  /ghn.html``    – Statusseite (Link-Raten, CPU/RAM, DOD, Profil)
4. ``GET  /device.html`` – Geräteseite (Uptime, FW-/HW-Version)

Umrechnung der Tabellenraten (wie im GUI-JavaScript):
``Mbps = floor(roh * 32 / 1000)``.

Ein Neustart läuft über dasselbe Formular-Muster wie der Login: ``POST /`` mit
``.SYSTEM.GENERAL.HW_RESET=1`` (Formular ``HW_RESET_FORM`` auf ``advanced.html``).
Das ist ein reiner Reboot – der destruktive Factory-Reset wird bewusst NICHT
implementiert.
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

# System-Statistik + NDIM (stehen ebenfalls auf ghn.html)
_RE_CPU = re.compile(r'id="system_stats_cpu_usage">\s*(\d+)')
_RE_MEM_FREE = re.compile(r'id="system_stats_free_memory">\s*(\d+)')
_RE_MEM_TOTAL = re.compile(r'id="system_stats_total_memory">\s*(\d+)')
_RE_DOD = re.compile(r'name="NODE\.GENERAL\.DOMAIN_ID"\s+value="([^"]*)"')
# Laufendes G.hn-Profil: sPhyMode ist eine ID aus dem mode-Array; der Index
# darin zeigt in das parallele profiles-Array (z. B. "COAX 200 MHz").
_RE_SPHYMODE = re.compile(r"var\s+sPhyMode\s*=\s*['\"]?(\d+)")
_RE_MODE_ARR = re.compile(r"var\s+mode\s*=\s*new\s+Array\(([^)]*)\)")
_RE_PROFILE_ARR = re.compile(r"var\s+profiles\s*=\s*new\s+Array\(([^)]*)\)")

# Geräteseite (device.html)
_RE_UPTIME = re.compile(r'id="device_sw_uptime">\s*([^<]+?)\s*<')
_RE_FW = re.compile(r'id="device_sw_version">\s*([^<]+?)\s*<')
_RE_HW = re.compile(r'id="device_hw_rev">\s*([^<]+?)\s*<')
_RE_UPTIME_PARTS = re.compile(
    r"(?:(\d+)\s*days?,\s*)?(\d+)\s*h\s*(\d+)\s*m\s*(\d+)\s*s"
)

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


def _parse_str_array(match: re.Match | None) -> list[str]:
    if not match:
        return []
    return [x.strip().strip('"').strip("'").strip() for x in match.group(1).split(",")]


def _parse_uptime_seconds(text: str | None) -> int | None:
    """'1 days, 13h 33m 33s' -> Sekunden."""
    if not text:
        return None
    m = _RE_UPTIME_PARTS.search(text)
    if not m:
        return None
    days, hours, mins, secs = (int(g) if g else 0 for g in m.groups())
    return ((days * 24 + hours) * 60 + mins) * 60 + secs


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
        """Login + ghn.html (+ device.html) holen und parsen."""
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

        data = self._parse(text)

        # device.html ist optional – schlägt der Abruf fehl, bleiben Uptime/FW/HW
        # None, der Rest der Sensoren funktioniert trotzdem weiter.
        try:
            dresp = await self._session.get(
                f"{self._base}/device.html", timeout=_TIMEOUT
            )
            if dresp.status == 200:
                data.update(self._parse_device(await dresp.text()))
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass

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

    @staticmethod
    def _parse_device(text: str) -> dict:
        m_up = _RE_UPTIME.search(text)
        m_fw = _RE_FW.search(text)
        m_hw = _RE_HW.search(text)
        return {
            "uptime_seconds": _parse_uptime_seconds(m_up.group(1) if m_up else None),
            "fw_version": m_fw.group(1).strip() if m_fw else None,
            "hw_version": m_hw.group(1).strip() if m_hw else None,
        }

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

        # System-Statistik
        m_cpu = _RE_CPU.search(text)
        m_free = _RE_MEM_FREE.search(text)
        m_total = _RE_MEM_TOTAL.search(text)
        mem_free = int(m_free.group(1)) if m_free else None
        mem_total = int(m_total.group(1)) if m_total else None
        mem_used_pct = (
            round((mem_total - mem_free) / mem_total * 100)
            if mem_total and mem_free is not None and mem_total > 0
            else None
        )

        # NDIM-Domain-ID (DOD)
        m_dod = _RE_DOD.search(text)

        # Laufendes Profil aus sPhyMode + mode/profiles-Arrays auflösen
        profile = None
        m_sphy = _RE_SPHYMODE.search(text)
        modes = _parse_str_array(_RE_MODE_ARR.search(text))
        profiles = _parse_str_array(_RE_PROFILE_ARR.search(text))
        if m_sphy and modes and profiles:
            sid = m_sphy.group(1)
            if sid in modes:
                idx = modes.index(sid)
                if idx < len(profiles):
                    profile = profiles[idx]

        return {
            "mac": mymac,
            "node_type": m_node.group(1).strip() if m_node else None,
            "domain": m_dom.group(1) if m_dom else None,
            "domain_id": m_dod.group(1) if m_dod else None,
            "profile": profile,
            "secured": (m_sec.group(1) == "YES") if m_sec else None,
            "speed_mbps": int(m_speed.group(1)) if m_speed else None,
            "cpu_pct": int(m_cpu.group(1)) if m_cpu else None,
            "mem_free_kb": mem_free,
            "mem_total_kb": mem_total,
            "mem_used_pct": mem_used_pct,
            "peers": peers,
            "peer_count": len(peers),
            "min_rate_mbps": min(rates) if rates else None,
        }
