"""Sensor platform for the Huawei Access Point integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import HuaweiApClientData
from .coordinator import HuaweiApCoordinator
from .entity import HuaweiApEntity


@dataclass(frozen=True, kw_only=True)
class HuaweiApSensorDescription(SensorEntityDescription):
    """Describes a Huawei AP sensor."""

    value_fn: Callable[[HuaweiApClientData], Any]
    attributes_fn: Callable[[HuaweiApClientData], dict[str, Any]] | None = None


def _client_attributes(data: HuaweiApClientData) -> dict[str, Any]:
    clients = data.clients or []
    return {
        "count": len(clients),
        "ssids": sorted({c.get("ssid") for c in clients if c.get("ssid")}),
        "clients": [
            {
                "mac": c.get("mac"),
                "ip": c.get("ip"),
                "ap": c.get("ap_name"),
                "ssid": c.get("ssid"),
                "band": c.get("band"),
                "rssi": c.get("rssi"),
            }
            for c in clients[:50]
        ],
    }


def _ap_attributes(data: HuaweiApClientData) -> dict[str, Any]:
    return {
        "access_points": [
            {
                "id": ap.get("id"),
                "name": ap.get("name"),
                "model": ap.get("model"),
                "ip": ap.get("ip"),
                "clients": ap.get("clients"),
                "is_leader": ap.get("is_leader"),
                "state": ap.get("state"),
                "uptime_seconds": ap.get("uptime_seconds"),
                "power_mode": ap.get("power_mode"),
            }
            for ap in (data.aps or [])
        ]
    }


def _radio_attributes(data: HuaweiApClientData) -> dict[str, Any]:
    return {
        "radios": [
            {
                "ap_id": r.get("ap_id"),
                "band": r.get("band"),
                "channel": r.get("channel"),
                "bandwidth": r.get("bandwidth"),
                "clients": r.get("clients"),
                "channel_utilization": r.get("channel_utilization"),
                "eirp": r.get("eirp"),
            }
            for r in (data.radios or [])
        ]
    }


def _interface_attributes(data: HuaweiApClientData) -> dict[str, Any]:
    interfaces = data.interfaces or []
    return {
        "up_count": sum(1 for i in interfaces if i.get("up")),
        "interfaces": [
            {
                "name": i.get("name"),
                "up": i.get("up"),
                "in_utilization": i.get("in_utilization"),
                "out_utilization": i.get("out_utilization"),
            }
            for i in interfaces
        ],
    }


def _leader_power_mode(data: HuaweiApClientData) -> str | None:
    """PoE class negotiated by the leader AP, e.g. ``AF(Limited)``."""
    aps = data.aps or []
    for ap in aps:
        if ap.get("is_leader"):
            return ap.get("power_mode")
    if aps:
        return aps[0].get("power_mode")
    return None


def _power_attributes(data: HuaweiApClientData) -> dict[str, Any]:
    return {
        "limited_count": data.power_limited_count,
        "access_points": [
            {
                "id": ap.get("id"),
                "name": ap.get("name"),
                "model": ap.get("model"),
                "power_mode": ap.get("power_mode"),
                "decided_by": ap.get("power_decided_by"),
            }
            for ap in (data.aps or [])
        ],
    }


SENSORS: tuple[HuaweiApSensorDescription, ...] = (
    HuaweiApSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: data.cpu_percent,
    ),
    HuaweiApSensorDescription(
        key="cpu_peak",
        translation_key="cpu_peak",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.cpu_max_percent,
    ),
    HuaweiApSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda data: data.memory_percent,
    ),
    HuaweiApSensorDescription(
        key="memory_used",
        translation_key="memory_used",
        native_unit_of_measurement="MB",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        entity_registry_enabled_default=False,
        value_fn=lambda data: (
            round(data.memory_used_kb / 1024, 1) if data.memory_used_kb else None
        ),
    ),
    HuaweiApSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.temperature,
    ),
    HuaweiApSensorDescription(
        key="temperature_max",
        translation_key="temperature_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.temperature_max,
    ),
    HuaweiApSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:clock-outline",
        value_fn=lambda data: data.uptime_seconds,
    ),
    HuaweiApSensorDescription(
        key="client_count",
        translation_key="client_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:account-multiple",
        value_fn=lambda data: data.client_count,
        attributes_fn=_client_attributes,
    ),
    HuaweiApSensorDescription(
        key="client_count_24g",
        translation_key="client_count_24g",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.client_count_24g,
        attributes_fn=_radio_attributes,
    ),
    HuaweiApSensorDescription(
        key="client_count_5g",
        translation_key="client_count_5g",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.client_count_5g,
    ),
    HuaweiApSensorDescription(
        key="ap_count",
        translation_key="ap_count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:access-point-network",
        value_fn=lambda data: data.ap_count,
        attributes_fn=_ap_attributes,
    ),
    HuaweiApSensorDescription(
        key="power_mode",
        translation_key="power_mode",
        icon="mdi:flash",
        value_fn=_leader_power_mode,
        attributes_fn=_power_attributes,
    ),
    HuaweiApSensorDescription(
        key="interfaces_up",
        translation_key="interfaces_up",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:ethernet",
        entity_registry_enabled_default=False,
        value_fn=lambda data: (
            sum(1 for i in (data.interfaces or []) if i.get("up"))
            if data.interfaces
            else None
        ),
        attributes_fn=_interface_attributes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Huawei AP sensors."""
    coordinator: HuaweiApCoordinator = entry.runtime_data
    async_add_entities(
        HuaweiApSensor(coordinator, description) for description in SENSORS
    )


class HuaweiApSensor(HuaweiApEntity, SensorEntity):
    """A single Huawei AP sensor."""

    entity_description: HuaweiApSensorDescription

    def __init__(
        self,
        coordinator: HuaweiApCoordinator,
        description: HuaweiApSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.coordinator.data is None or not self.entity_description.attributes_fn:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
