"""Button platform for the Huawei Access Point integration.

Warning: pressing the restart button reboots the AP. Every client on every AP
managed by this device will drop for roughly one to two minutes.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HuaweiApCoordinator
from .entity import HuaweiApEntity

_LOGGER = logging.getLogger(__name__)

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        icon="mdi:restart",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Huawei AP buttons."""
    coordinator: HuaweiApCoordinator = entry.runtime_data
    async_add_entities(
        HuaweiApButton(coordinator, description) for description in BUTTONS
    )


class HuaweiApButton(HuaweiApEntity, ButtonEntity):
    """A Huawei AP action button."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: HuaweiApCoordinator,
        description: ButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    async def async_press(self) -> None:
        """Reboot the device."""
        _LOGGER.warning(
            "正在重启华为 AP %s，所有接入终端将短暂断网",
            self.coordinator.client.host,
        )
        await self.coordinator.async_restart_device()
