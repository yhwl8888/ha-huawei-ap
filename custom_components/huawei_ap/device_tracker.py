"""Device tracker platform - one entity per associated Wi-Fi client.

The AP exposes its association table via ``display station all``, which this
platform turns into router-type device trackers. Clients are never removed
once discovered: when a client disappears from the table the entity flips to
``not_home`` instead of vanishing from the registry.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import (
    SourceType,
    TrackerEntity,
)
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HuaweiApCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device trackers for every associated client."""
    coordinator: HuaweiApCoordinator = entry.runtime_data
    tracked: dict[str, HuaweiClientTracker] = {}

    @callback
    def _sync_entities() -> None:
        data = coordinator.data
        if data is None or not data.clients:
            return
        new_entities: list[HuaweiClientTracker] = []
        for client in data.clients:
            mac = client.get("mac")
            if not mac or mac in tracked:
                continue
            entity = HuaweiClientTracker(coordinator, mac)
            tracked[mac] = entity
            new_entities.append(entity)
        if new_entities:
            _LOGGER.debug("新增 %d 个终端追踪实体", len(new_entities))
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class HuaweiClientTracker(TrackerEntity):
    """A Wi-Fi client seen by the AP."""

    _attr_has_entity_name = True
    _attr_source_type = SourceType.ROUTER
    _attr_should_poll = False

    def __init__(self, coordinator: HuaweiApCoordinator, mac: str) -> None:
        self.coordinator = coordinator
        self._mac = mac
        self._host = coordinator.client.host
        self._attr_unique_id = f"{DOMAIN}_{self._host}_sta_{mac.replace(':', '').lower()}"
        self._attr_name = f"终端 {mac}"

    # ------------------------------------------------------------------
    def _current(self) -> dict | None:
        data = self.coordinator.data
        if not data or not data.clients:
            return None
        for client in data.clients:
            if client.get("mac") == self._mac:
                return client
        return None

    # ------------------------------------------------------------------
    @property
    def device_info(self):
        from homeassistant.helpers.device_registry import DeviceInfo

        return DeviceInfo(identifiers={(DOMAIN, self._host)})

    @property
    def mac(self) -> str:
        return self._mac

    @property
    def ip(self) -> str | None:
        client = self._current()
        return client.get("ip") if client else None

    @property
    def is_connected(self) -> bool:
        return self._current() is not None

    @property
    def location_name(self) -> str:
        return STATE_HOME if self.is_connected else STATE_NOT_HOME

    @property
    def available(self) -> bool:
        # The tracker stays available even when the client is away, so the
        # entity keeps its history instead of going unavailable.
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        client = self._current()
        if not client:
            return {"mac": self._mac}
        return {
            "mac": client.get("mac"),
            "ip": client.get("ip"),
            "ssid": client.get("ssid"),
            "ap": client.get("ap_name"),
            "band": client.get("band"),
            "phy": client.get("phy"),
            "rssi": client.get("rssi"),
            "rx_mbps": client.get("rx_mbps"),
            "tx_mbps": client.get("tx_mbps"),
            "vlan": client.get("vlan"),
        }
