"""Reboot-Button für die G.hn-Adapter (Hardware-Reset, kein Factory-Reset)."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GhnConfigEntry
from .api import GhnError
from .const import DOMAIN
from .entity import GhnEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GhnConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([GhnRebootButton(entry.runtime_data)])


class GhnRebootButton(GhnEntity, ButtonEntity):
    """Löst einen Hardware-Reset (Neustart) des Adapters aus.

    Achtung: Ein Neustart des Domain-Masters trennt kurzzeitig das gesamte
    Koax-Backbone (alle Slaves verlieren die Domain).
    """

    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.async_reboot()
        except GhnError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="reboot_failed",
                translation_placeholders={"error": str(err)},
            ) from err
