"""Verbindungs-Binärsensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GhnConfigEntry
from .coordinator import GhnCoordinator
from .entity import GhnEntity

# Alle Werte stammen aus einem gemeinsamen Coordinator-Poll.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GhnConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([GhnConnectivity(entry.runtime_data)])


class GhnConnectivity(GhnEntity, BinarySensorEntity):
    """Ist der Adapter erreichbar/eingeloggt?"""

    _attr_translation_key = "connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: GhnCoordinator) -> None:
        super().__init__(coordinator, "connectivity")

    @property
    def available(self) -> bool:
        # Bewusst immer verfügbar, damit der Sensor bei Verlust auf "off"
        # geht (statt "unavailable") – passt zum Watchdog-Muster.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success
