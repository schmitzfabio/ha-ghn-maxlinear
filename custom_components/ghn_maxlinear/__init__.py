"""Die G.hn-MaxLinear-Integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import GhnCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

type GhnConfigEntry = ConfigEntry[GhnCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GhnConfigEntry) -> bool:
    coordinator = GhnCoordinator(hass, entry)

    # Bewusst KEIN async_config_entry_first_refresh(): das würde bei einem
    # beim HA-Start nicht erreichbaren Adapter ConfigEntryNotReady werfen und
    # gar keine Entitäten anlegen – ausgerechnet der Verbindungssensor, der
    # genau diesen Fall melden soll, wäre dann nicht vorhanden. Stattdessen
    # wird die Integration geladen und der Sensor meldet "off".
    # Ein Auth-Fehler startet über den Coordinator weiterhin den Reauth-Flow.
    await coordinator.async_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GhnConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
