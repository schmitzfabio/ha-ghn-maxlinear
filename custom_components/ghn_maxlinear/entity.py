"""Gemeinsame Basis-Entity (Device-Gruppierung)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GhnCoordinator


class GhnEntity(CoordinatorEntity[GhnCoordinator]):
    """Basisklasse mit Device-Info."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GhnCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        base = coordinator.device_base_id
        self._attr_unique_id = f"{base}_{key}"

        data = coordinator.data or {}
        connections = set()
        mac = data.get("mac")
        if mac:
            connections.add((CONNECTION_NETWORK_MAC, mac))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, base)},
            connections=connections,
            name=entry.title,
            manufacturer="MaxLinear",
            model="G.hn Adapter",
            sw_version=data.get("fw_version"),
            hw_version=data.get("hw_version"),
            configuration_url=f"http://{entry.data[CONF_HOST]}/",
        )
