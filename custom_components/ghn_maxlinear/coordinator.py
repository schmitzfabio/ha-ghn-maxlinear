"""DataUpdateCoordinator für die G.hn-Adapter."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GhnAuthError, GhnClient, GhnConnectionError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GhnCoordinator(DataUpdateCoordinator[dict]):
    """Pollt einen MaxLinear-G.hn-Adapter."""

    # Wird von super().__init__(config_entry=...) gesetzt; die Annotation
    # verengt nur den Optional-Typ der Basisklasse.
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=timedelta(
                seconds=entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
            ),
        )
        # Stabile Basis für unique_id und Device-Identifier.
        self.device_base_id = entry.unique_id or entry.entry_id
        self.client = GhnClient(
            entry.data[CONF_HOST],
            entry.data[CONF_PASSWORD],
            async_get_clientsession(hass),
        )

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_get_data()
        except GhnAuthError as err:
            # Kein UpdateFailed: sonst würde HA im Minutentakt weiter ein
            # falsches Passwort posten, statt den Reauth-Dialog zu zeigen.
            raise ConfigEntryAuthFailed(
                f"Authentifizierung fehlgeschlagen: {err}"
            ) from err
        except GhnConnectionError as err:
            raise UpdateFailed(str(err)) from err
