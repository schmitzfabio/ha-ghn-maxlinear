"""Diagnosedaten für einen Config-Entry.

Diese Daten hängen Nutzer typischerweise an Issues an – Passwort, MACs und
Host werden deshalb redigiert.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import GhnConfigEntry

# "mac" trifft auch die MACs in der verschachtelten peers-Liste.
TO_REDACT = {CONF_PASSWORD, CONF_HOST, "mac", "domain", "domain_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GhnConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
