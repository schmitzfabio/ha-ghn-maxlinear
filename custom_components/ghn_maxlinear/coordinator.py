"""DataUpdateCoordinator für die G.hn-Adapter."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GhnAuthError, GhnClient, GhnConnectionError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GhnCoordinator(DataUpdateCoordinator[dict]):
    """Pollt einen MaxLinear-G.hn-Adapter."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.client = GhnClient(
            entry.data[CONF_HOST],
            entry.data[CONF_PASSWORD],
            async_get_clientsession(hass),
        )

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_get_data()
        except GhnAuthError as err:
            raise UpdateFailed(f"Authentifizierung fehlgeschlagen: {err}") from err
        except GhnConnectionError as err:
            raise UpdateFailed(str(err)) from err
