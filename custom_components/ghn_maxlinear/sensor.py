"""Sensoren für die G.hn-Adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import GhnConfigEntry
from .coordinator import GhnCoordinator
from .entity import GhnEntity

# Alle Werte stammen aus einem gemeinsamen Coordinator-Poll.
PARALLEL_UPDATES = 0

# Der berechnete Boot-Zeitpunkt (jetzt - Uptime) jittert um ein paar Sekunden pro
# Poll. Erst ab dieser Abweichung gilt er als "echter" Neustart und wird neu
# gemeldet – das vermeidet dauerndes Flattern im Recorder.
_UPTIME_DRIFT = timedelta(seconds=120)


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
        value_fn=lambda d: d.get("speed_mbps"),
    ),
    GhnSensorDescription(
        key="min_rate",
        translation_key="min_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("min_rate_mbps"),
        attrs_fn=lambda d: {"peers": d.get("peers", [])},
    ),
    GhnSensorDescription(
        key="peer_count",
        translation_key="peer_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("peer_count"),
    ),
    GhnSensorDescription(
        key="node_type",
        translation_key="node_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("node_type"),
        attrs_fn=lambda d: {
            "domain_name": d.get("domain"),
            "domain_id": d.get("domain_id"),
            "profile": d.get("profile"),
            "secured": d.get("secured"),
            "mac": d.get("mac"),
        },
    ),
    GhnSensorDescription(
        key="cpu",
        translation_key="cpu",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("cpu_pct"),
    ),
    GhnSensorDescription(
        key="memory",
        translation_key="memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("mem_used_pct"),
        attrs_fn=lambda d: {
            "free_kb": d.get("mem_free_kb"),
            "total_kb": d.get("mem_total_kb"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GhnConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [GhnSensor(coordinator, desc) for desc in SENSORS]
    entities.append(GhnUptimeSensor(coordinator))
    async_add_entities(entities)


class GhnSensor(GhnEntity, SensorEntity):
    """Ein einzelner G.hn-Wert."""

    entity_description: GhnSensorDescription

    # Die Peer-Liste (und die übrigen Zusatzattribute) ändert sich bei jedem
    # Poll und würde die Recorder-Datenbank mit einem kompletten JSON-Blob pro
    # Minute füllen, ohne dass die Historie davon profitiert.
    _unrecorded_attributes = frozenset(
        {
            "peers",
            "free_kb",
            "total_kb",
            "domain_name",
            "domain_id",
            "profile",
            "secured",
            "mac",
        }
    )

    def __init__(
        self, coordinator: GhnCoordinator, description: GhnSensorDescription
    ) -> None:
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


class GhnUptimeSensor(GhnEntity, RestoreSensor):
    """Boot-Zeitpunkt des Adapters (jetzt - Uptime), stabilisiert.

    Meldet einen Timestamp statt hochzählender Sekunden – so erkennt eine
    Automation einen unerwarteten Neustart am Sprung des Werts. Der Wert
    überlebt HA-Neustarts, sonst würde er dort jedes Mal um den Poll-Jitter
    springen und einen Geräte-Neustart vortäuschen.
    """

    _attr_translation_key = "uptime"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: GhnCoordinator) -> None:
        super().__init__(coordinator, "uptime")
        self._boot_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_sensor_data()
        if restored is not None and isinstance(restored.native_value, datetime):
            self._boot_time = restored.native_value
        # Weicht der frisch berechnete Wert stark ab, hat das Gerät während
        # der HA-Auszeit tatsächlich neu gestartet – dann gewinnt der neue.
        self._update_boot_time()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_boot_time()
        super()._handle_coordinator_update()

    @callback
    def _update_boot_time(self) -> None:
        data = self.coordinator.data or {}
        secs = data.get("uptime_seconds")
        if secs is None:
            return
        boot = dt_util.utcnow() - timedelta(seconds=secs)
        # Nur bei echtem Sprung (Neustart) aktualisieren, sonst alten Wert halten.
        if self._boot_time is None or abs(boot - self._boot_time) > _UPTIME_DRIFT:
            self._boot_time = boot

    @property
    def native_value(self) -> datetime | None:
        return self._boot_time
