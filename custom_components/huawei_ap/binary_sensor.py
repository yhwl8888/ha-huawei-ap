"""Binary sensor platform for the Huawei Access Point integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HuaweiApCoordinator
from .entity import HuaweiApEntity

BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="reachable",
        translation_key="reachable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="power_insufficient",
        translation_key="power_insufficient",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:flash-alert",
    ),
    BinarySensorEntityDescription(
        key="temperature_alarm",
        translation_key="temperature_alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:thermometer-alert",
    ),
    BinarySensorEntityDescription(
        key="clients_present",
        translation_key="clients_present",
        icon="mdi:wifi-check",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Huawei AP binary sensors."""
    coordinator: HuaweiApCoordinator = entry.runtime_data
    async_add_entities(
        HuaweiApBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class HuaweiApBinarySensor(HuaweiApEntity, BinarySensorEntity):
    """A Huawei AP binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: HuaweiApCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        key = self.entity_description.key

        if key == "reachable":
            return self.coordinator.last_update_success
        if data is None:
            return None
        if key == "power_insufficient":
            return data.power_insufficient
        if key == "temperature_alarm":
            return data.temperature_alarm
        if key == "clients_present":
            if data.client_count is None:
                return None
            return data.client_count > 0
        return None
