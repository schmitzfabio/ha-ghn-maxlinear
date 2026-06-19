"""Sensoren für die G.hn-Adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GhnConfigEntry
from .entity import GhnEntity


@dataclass(frozen=True, kw_only=True)
class GhnSensorDescription(SensorEntityDescription):
    """Beschreibung eines G.hn-Sensors."""

    value_fn: Callable[[dict], float | int | str | None]
    attrs_fn: Callable[[dict], dict] | None = None


SENSORS: tuple[GhnSensorDescription, ...] = (
    GhnSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        value_fn=lambda d: d.get("speed_mbps"),
    ),
    GhnSensorDescription(
        key="min_rate",
        translation_key="min_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        value_fn=lambda d: d.get("min_rate_mbps"),
        attrs_fn=lambda d: {"peers": d.get("peers", [])},
    ),
    GhnSensorDescription(
        key="peer_count",
        translation_key="peer_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lan",
        value_fn=lambda d: d.get("peer_count"),
    ),
    GhnSensorDescription(
        key="node_type",
        translation_key="node_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:lan-connect",
        value_fn=lambda d: d.get("node_type"),
        attrs_fn=lambda d: {
            "domain_name": d.get("domain"),
            "secured": d.get("secured"),
            "mac": d.get("mac"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GhnConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(GhnSensor(coordinator, desc) for desc in SENSORS)


class GhnSensor(GhnEntity, SensorEntity):
    """Ein einzelner G.hn-Wert."""

    entity_description: GhnSensorDescription

    def __init__(self, coordinator, description: GhnSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        if self.coordinator.data is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
