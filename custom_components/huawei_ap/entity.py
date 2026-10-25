"""Shared entity base for the Huawei Access Point integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HuaweiApCoordinator


class HuaweiApEntity(CoordinatorEntity[HuaweiApCoordinator]):
    """Common behaviour for all Huawei AP entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HuaweiApCoordinator, key: str) -> None:
        super().__init__(coordinator)
        host = coordinator.client.host
        self._attr_unique_id = f"{DOMAIN}_{host}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        host = self.coordinator.client.host

        model = data.model if data and data.model else None
        if model:
            name = f"Huawei {model}"
        else:
            name = f"Huawei AP {host}"

        return DeviceInfo(
            identifiers={(DOMAIN, host)},
            manufacturer=MANUFACTURER,
            model=model,
            name=name,
            sw_version=data.firmware if data else None,
            serial_number=data.serial if data else None,
            connections=(
                {(CONNECTION_NETWORK_MAC, data.mac)}
                if data and data.mac
                else set()
            ),
            configuration_url=f"https://{host}",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
